"""
Core attendance business logic (PRD §5.1, §5.2, §5.3):
  - Confidence + liveness gates (§6.3)
  - Per-track cooldown (§6.3)
  - Check-in / check-out state machine with direction-aware camera
  - Late arrival, early leave, overtime_seconds (§5.1)
  - Blacklist, VIP, after-hours, restricted-area, unknown-person alerts (§5.3)
  - Occupancy counter (enter/exit) (§5.2, §5.4)
  - Loitering detection (§5.3)
  - Visitor / unknown detection logging (§5.2)
"""
import logging
import json, uuid
from datetime import datetime, date, timedelta, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import pytz

from ..models import (
    Employee, Branch, Shift, EmployeeShift,
    AttendanceLog, RecognitionEvent, Camera, UnknownDetection,
)
from ..config import settings
from .alert_service import AlertService, OccupancyService


logger = logging.getLogger(__name__)


class AttendanceService:
    def __init__(self, db: AsyncSession, redis=None):
        self.db = db
        self.redis = redis
        self.alerts = AlertService(db, redis)
        self.occupancy = OccupancyService(redis)

    # ── Main entry point ───────────────────────────────────────────────────
    async def process_recognition_event(self, event: dict, tenant_id: uuid.UUID) -> dict:
        conf = float(event.get("confidence", 0))
        try:
            camera_id = uuid.UUID(str(event["camera_id"])) if event.get("camera_id") else None
        except (ValueError, KeyError):
            camera_id = None

        # ── Suspicious object event (bag, suitcase, backpack near person) ──
        if event.get("type") == "suspicious_object":
            label = event.get("object_label", "suspicious object")
            cam = await self.db.get(Camera, camera_id) if camera_id else None
            cam_name = cam.name if cam else "a camera"
            await self.alerts.fire(
                tenant_id, "suspicious_object",
                f"A {label} was spotted near someone on {cam_name}. Please check the area.",
                camera_id=camera_id, snapshot_url=event.get("snapshot_url"),
            )
            await self.db.commit()
            return {"action": "skip", "reason": "suspicious_object", "label": label}

        # ── Masked face event ──────────────────────────────────────────────
        if event.get("type") == "masked_face":
            cam = await self.db.get(Camera, camera_id) if camera_id else None
            cam_name = cam.name if cam else "a camera"
            await self.alerts.fire(
                tenant_id, "masked_face",
                f"Someone wearing a face covering was seen on {cam_name}. Identity could not be confirmed.",
                camera_id=camera_id, snapshot_url=event.get("snapshot_url"),
            )
            await self.db.commit()
            return {"action": "skip", "reason": "masked_face"}

        # PRD §6.3: liveness gate at 0.80
        if not event.get("is_live", True):
            logger.warning("spoof_detected cam=%s conf=%.3f", camera_id, conf)
            _spoof_cam = await self.db.get(Camera, camera_id) if camera_id else None
            _spoof_cam_name = _spoof_cam.name if _spoof_cam else "a camera"
            await self.alerts.fire(
                tenant_id, "spoof_attempt",
                f"Someone tried to use a photo or screen to fool the camera on {_spoof_cam_name}. Access was blocked.",
                camera_id=camera_id, snapshot_url=event.get("snapshot_url"),
            )
            await self._store_event(event, tenant_id)
            await self.db.commit()
            return {"action": "skip", "reason": "spoof_detected"}

        # Restricted-area check (PRD §5.3): fires even if unknown
        cam = await self.db.get(Camera, camera_id) if camera_id else None
        if cam and cam.is_restricted:
            await self.alerts.fire(
                tenant_id, "restricted_area",
                f"Someone entered a restricted area monitored by {cam.name}. Please verify authorisation.",
                camera_id=camera_id, snapshot_url=event.get("snapshot_url"),
            )

        # PRD §6.3: confidence gate → unknown person path
        # Also catches unknown_person events from edge (employee_id is None)
        if not event.get("employee_id") or conf < settings.CONFIDENCE_THRESHOLD:
            if not event.get("employee_id"):
                logger.warning("unknown_person cam=%s conf=%.3f — no employee matched", camera_id, conf)
            else:
                logger.warning("low_confidence cam=%s conf=%.3f threshold=%.2f — skipped",
                               camera_id, conf, settings.CONFIDENCE_THRESHOLD)
            await self._handle_unknown(event, tenant_id, cam)
            await self.db.commit()
            return {"action": "skip", "reason": "unknown_person", "confidence": conf}

        try:
            emp_id = uuid.UUID(str(event["employee_id"]))
        except (ValueError, KeyError):
            return {"action": "skip", "reason": "invalid_employee_id"}
        employee = await self.db.get(Employee, emp_id)
        if not employee or not employee.is_active:
            logger.warning("employee_not_found_or_inactive emp=%s", emp_id)
            return {"action": "skip", "reason": "employee_inactive"}

        # Cooldown (PRD §6.3: 5 min per person per camera)
        if self.redis:
            ck = f"cooldown:{emp_id}:{camera_id}"
            if await self.redis.get(ck):
                logger.debug("cooldown active emp=%s cam=%s", emp_id, camera_id)
                return {"action": "skip", "reason": "cooldown"}

        rec = await self._store_event(event, tenant_id)

        # PRD §5.3: blacklist alert
        if employee.is_blacklisted:
            await self.alerts.fire(
                tenant_id, "blacklist",
                f"{employee.full_name} has been spotted on camera — this person is on the blocked list. Immediate attention required.",
                employee_id=emp_id, camera_id=camera_id,
                snapshot_url=event.get("snapshot_url"),
            )

        # PRD §5.3: VIP alert (different Slack channel)
        if employee.is_vip:
            await self.alerts.fire(
                tenant_id, "vip",
                f"{employee.full_name} has arrived.",
                employee_id=emp_id, camera_id=camera_id,
                snapshot_url=event.get("snapshot_url"),
            )

        # Shift + timezone
        _branch = await self.db.get(Branch, employee.branch_id) if employee.branch_id else None
        tz = pytz.timezone(_branch.timezone if _branch else "UTC")
        now_local = datetime.now(tz)
        today = now_local.date()
        shift = await self._get_current_shift(emp_id, today)

        # PRD §5.3: after-hours alert
        if shift:
            await self._check_after_hours(
                shift, now_local, tz, today, tenant_id, employee, cam
            )

        # PRD §5.3: loitering
        if cam:
            await self.alerts.check_loitering(
                tenant_id, emp_id, camera_id, employee.full_name,
                event.get("snapshot_url"),
            )

        log = await self._get_or_create_log(employee, today, shift, tenant_id)

        cam_direction = event.get("direction") or (cam.direction if cam else "entrance")
        if log.check_in_at is None:
            action = "check_in"
        elif cam_direction == "exit":
            action = "check_out"
        else:
            action = "skip_duplicate"

        if action == "check_in":
            log.check_in_at = datetime.now(timezone.utc)
            log.check_in_source = "camera"
            log.status = "present"
            if shift:
                scheduled = tz.localize(datetime.combine(today, shift.start_time))
                late_min = (now_local - (scheduled + timedelta(minutes=shift.grace_in_min))).total_seconds() / 60
                if late_min > 0:
                    log.is_late = True
                    log.late_by_min = int(late_min)
                    log.status = "late"
                    from .notification_service import NotificationService
                    await NotificationService().notify_late(employee.full_name, int(late_min))
            # PRD §5.2: occupancy +1 on entrance
            zone = (cam.camera_zone if cam else None) or str(employee.branch_id or "default")
            await self.occupancy.enter(tenant_id, zone)

        elif action == "check_out":
            log.check_out_at = datetime.now(timezone.utc)
            log.check_out_source = "camera"
            if log.check_in_at:
                hrs = (log.check_out_at - log.check_in_at).total_seconds() / 3600
                log.working_hours = round(hrs, 2)
            if shift:
                scheduled_out = tz.localize(datetime.combine(today, shift.end_time))
                # PRD §5.1: early leave
                early_min = ((scheduled_out - timedelta(minutes=shift.early_out_min)) - now_local).total_seconds() / 60
                if early_min > 0:
                    log.is_early_leave = True
                    log.early_by_min = int(early_min)
                # PRD §5.1: overtime_seconds = seconds past shift end
                ot_sec = (now_local - scheduled_out).total_seconds()
                if ot_sec > 0:
                    log.overtime_seconds = int(ot_sec)
            # PRD §5.2: occupancy -1 on exit
            zone = (cam.camera_zone if cam else None) or str(employee.branch_id or "default")
            await self.occupancy.exit(tenant_id, zone)
            if cam:
                await self.alerts.clear_loitering(tenant_id, emp_id, camera_id)

        elif action == "skip_duplicate":
            return {"action": "skip", "reason": "already_checked_in"}

        await self.db.commit()
        logger.info("attendance %s emp=%s (%s) conf=%.3f cam=%s", action, emp_id, employee.full_name, conf, camera_id)

        if self.redis:
            await self.redis.setex(f"cooldown:{emp_id}:{camera_id}", settings.COOLDOWN_MINUTES * 60, "1")

        result = {
            "action": action,
            "employee_id": str(emp_id),
            "employee_name": employee.full_name,
            "department": employee.department,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "confidence": conf,
            "camera_id": str(camera_id) if camera_id else None,
            "direction": cam_direction,
            "status": log.status,
            "is_late": log.is_late,
            "late_by_min": log.late_by_min,
            "is_early_leave": log.is_early_leave,
            "early_by_min": log.early_by_min,
            "overtime_seconds": log.overtime_seconds,
            "snapshot_url": event.get("snapshot_url"),
        }
        if self.redis:
            await self.redis.publish(f"attendance:{tenant_id}", json.dumps(result))
            await self.redis.lpush(f"attendance:live:{tenant_id}", json.dumps(result))
            await self.redis.ltrim(f"attendance:live:{tenant_id}", 0, 99)
        return result

    # ── After-hours check (PRD §5.3) ──────────────────────────────────────
    async def _check_after_hours(self, shift, now_local, tz, today, tenant_id, employee, cam):
        from datetime import time as dtime
        buffer = timedelta(minutes=settings.AFTER_HOURS_BUFFER_MIN)
        shift_start = tz.localize(datetime.combine(today, shift.start_time))
        shift_end   = tz.localize(datetime.combine(today, shift.end_time))
        is_work_day = now_local.isoweekday() in (shift.work_days or [1, 2, 3, 4, 5])
        outside = not is_work_day or now_local < (shift_start - buffer) or now_local > (shift_end + buffer)
        if outside:
            await self.alerts.fire(
                tenant_id, "after_hours",
                f"{employee.full_name} was seen on camera outside their scheduled shift hours. This may need a follow-up.",
                employee_id=employee.id,
                camera_id=cam.id if cam else None,
            )

    # ── Unknown / intruder path (PRD §5.2, §5.3) ──────────────────────────
    async def _handle_unknown(self, event: dict, tenant_id: uuid.UUID, cam):
        from datetime import date as _date
        cam_uuid = cam.id if cam else self._safe_uuid(event.get("camera_id"))
        ud = UnknownDetection(
            tenant_id=tenant_id,
            camera_id=cam_uuid,
            track_id=event.get("track_id"),
            snapshot_url=event.get("snapshot_url"),
            confidence_best=event.get("confidence"),
            detection_date=_date.today(),
            detection_timestamp=datetime.now(timezone.utc),
        )
        self.db.add(ud)
        await self.db.flush()

        cam_name = cam.name if cam else "camera"

        # Always fire unknown_person alert so dashboard shows it immediately
        await self.alerts.fire(
            tenant_id, "unknown_person",
            f"An unrecognised person was spotted on {cam_name}. They are not in the system.",
            camera_id=cam_uuid,
            snapshot_url=event.get("snapshot_url"),
        )

        # PRD §5.3: escalate to intruder alert if outside business hours in local time
        import pytz as _pytz
        try:
            _tz = _pytz.timezone("UTC")  # fallback; replace with branch.timezone when available
            _now_local = datetime.now(_tz)
        except Exception:
            _now_local = datetime.now(timezone.utc)
        hour = _now_local.hour
        if hour < 7 or hour >= 20:
            await self.alerts.fire(
                tenant_id, "intruder",
                f"An unidentified person was spotted on {cam_name} outside of working hours. Please investigate immediately.",
                camera_id=cam_uuid,
                snapshot_url=event.get("snapshot_url"),
            )

    # ── DB helpers ────────────────────────────────────────────────────────
    @staticmethod
    def _safe_uuid(val) -> "uuid.UUID | None":
        if not val:
            return None
        try:
            return uuid.UUID(str(val))
        except (ValueError, AttributeError):
            return None

    async def _store_event(self, event: dict, tenant_id: uuid.UUID) -> RecognitionEvent:
        rec = RecognitionEvent(
            tenant_id=tenant_id,
            camera_id=self._safe_uuid(event.get("camera_id")),
            employee_id=self._safe_uuid(event.get("employee_id")),
            track_id=event.get("track_id"),
            confidence=event.get("confidence", 0),
            is_live=event.get("is_live", True),
            spoof_score=event.get("spoof_score"),
            snapshot_url=event.get("snapshot_url"),
            embedding_dist=event.get("embedding_dist"),
            raw_event=event,
        )
        self.db.add(rec)
        await self.db.flush()
        return rec

    async def _get_current_shift(self, emp_id: uuid.UUID, day: date):
        stmt = (
            select(Shift).join(EmployeeShift, EmployeeShift.shift_id == Shift.id)
            .where(
                EmployeeShift.employee_id == emp_id,
                EmployeeShift.effective_from <= day,
                (EmployeeShift.effective_to.is_(None)) | (EmployeeShift.effective_to > day),
                Shift.is_active.is_(True),
            )
            .order_by(EmployeeShift.effective_from.desc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _get_or_create_log(self, employee, day, shift, tenant_id):
        stmt = select(AttendanceLog).where(
            AttendanceLog.employee_id == employee.id,
            AttendanceLog.attendance_date == day,
        )
        log = (await self.db.execute(stmt)).scalar_one_or_none()
        if log is None:
            log = AttendanceLog(
                tenant_id=tenant_id, employee_id=employee.id,
                branch_id=employee.branch_id,
                shift_id=shift.id if shift else None,
                attendance_date=day, status="present",
            )
            self.db.add(log)
            await self.db.flush()
        return log

    # ── Reports / Summaries ───────────────────────────────────────────────
    async def get_summary(self, day: date, tenant_id: uuid.UUID, branch_id=None) -> dict:
        total_q = select(func.count(Employee.id)).where(
            Employee.tenant_id == tenant_id, Employee.is_active.is_(True)
        )
        if branch_id:
            total_q = total_q.where(Employee.branch_id == branch_id)
        total = (await self.db.execute(total_q)).scalar() or 0
        logs_q = select(AttendanceLog).where(
            AttendanceLog.tenant_id == tenant_id, AttendanceLog.attendance_date == day
        )
        if branch_id:
            logs_q = logs_q.where(AttendanceLog.branch_id == branch_id)
        logs = (await self.db.execute(logs_q)).scalars().all()
        present = sum(1 for l in logs if l.status in ("present", "late"))
        return {
            "date": day, "total_employees": total,
            "present": present, "absent": max(total - present, 0),
            "late": sum(1 for l in logs if l.is_late),
            "early_leave": sum(1 for l in logs if l.is_early_leave),
            "attendance_rate": round(present / total * 100, 1) if total else 0.0,
        }

    async def get_logs(self, tenant_id, branch_id, employee_id, date_from, date_to, page, page_size):
        stmt = select(AttendanceLog).where(
            AttendanceLog.tenant_id == tenant_id,
            AttendanceLog.attendance_date >= date_from,
            AttendanceLog.attendance_date <= date_to,
        )
        if branch_id:
            stmt = stmt.where(AttendanceLog.branch_id == branch_id)
        if employee_id:
            stmt = stmt.where(AttendanceLog.employee_id == employee_id)
        stmt = stmt.order_by(AttendanceLog.check_in_at.desc()).offset((page - 1) * page_size).limit(page_size)
        return (await self.db.execute(stmt)).scalars().all()

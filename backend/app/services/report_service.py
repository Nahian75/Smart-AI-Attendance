"""Attendance reporting & CSV/analytics aggregation."""
import csv
import io
import uuid
from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AttendanceLog, Employee


class ReportService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def monthly_csv(self, tenant_id: uuid.UUID, year: int, month: int) -> str:
        start = date(year, month, 1)
        end = date(year + (month == 12), (month % 12) + 1, 1)
        stmt = (
            select(AttendanceLog, Employee)
            .join(Employee, Employee.id == AttendanceLog.employee_id)
            .where(
                AttendanceLog.tenant_id == tenant_id,
                AttendanceLog.attendance_date >= start,
                AttendanceLog.attendance_date < end,
            )
            .order_by(AttendanceLog.attendance_date)
        )
        rows = (await self.db.execute(stmt)).all()

        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Date", "Employee", "Code", "Dept", "Check In", "Check Out",
                    "Status", "Late (min)", "Hours"])
        for log, emp in rows:
            w.writerow([
                log.attendance_date, emp.full_name, emp.employee_code or "",
                emp.department or "",
                log.check_in_at.strftime("%H:%M") if log.check_in_at else "",
                log.check_out_at.strftime("%H:%M") if log.check_out_at else "",
                log.status, log.late_by_min, log.working_hours or 0,
            ])
        return buf.getvalue()

    async def weekly_rates(self, tenant_id: uuid.UUID, days: list[date]) -> list[dict]:
        out = []
        for d in days:
            logs = (await self.db.execute(
                select(AttendanceLog).where(
                    AttendanceLog.tenant_id == tenant_id,
                    AttendanceLog.attendance_date == d,
                )
            )).scalars().all()
            present = sum(1 for l in logs if l.status in ("present", "late"))
            total = (await self.db.execute(
                select(Employee).where(Employee.tenant_id == tenant_id, Employee.is_active.is_(True))
            )).scalars().all()
            total_n = len(total)
            out.append({"date": d.isoformat(),
                        "rate": round(present / total_n * 100, 1) if total_n else 0})
        return out

    async def shift_compliance(self, tenant_id: uuid.UUID) -> list[dict]:
        """Calculate shift compliance for current week."""
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        today = datetime.now(ZoneInfo("UTC")).date()
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)

        logs = (await self.db.execute(
            select(AttendanceLog, Employee)
            .join(Employee, Employee.id == AttendanceLog.employee_id)
            .where(
                AttendanceLog.tenant_id == tenant_id,
                AttendanceLog.attendance_date >= monday,
                AttendanceLog.attendance_date <= sunday,
            )
        )).all()

        result = {}
        for log, emp in logs:
            emp_id = str(emp.id)
            if emp_id not in result:
                result[emp_id] = {
                    "employee_id": emp_id,
                    "name": emp.full_name,
                    "dept": emp.department or "",
                    "on_time": 0,
                    "late": 0,
                    "on_time_pct": 0,
                }
            if log.status == "late":
                result[emp_id]["late"] += 1
            else:
                result[emp_id]["on_time"] += 1

        for emp_id in result:
            total = result[emp_id]["on_time"] + result[emp_id]["late"]
            result[emp_id]["on_time_pct"] = round(
                result[emp_id]["on_time"] / total * 100 if total else 0, 1
            )

        return list(result.values())

    async def per_camera_analytics(
        self,
        tenant_id: uuid.UUID,
        start_date: date,
        end_date: date,
        camera_id: uuid.UUID | None = None,
    ) -> list[dict]:
        """Get analytics filtered by camera."""
        stmt = (
            select(AttendanceLog)
            .where(
                AttendanceLog.tenant_id == tenant_id,
                AttendanceLog.attendance_date >= start_date,
                AttendanceLog.attendance_date <= end_date,
            )
        )
        if camera_id:
            stmt = stmt.where(AttendanceLog.check_in_source == str(camera_id))

        logs = (await self.db.execute(stmt)).scalars().all()

        camera_stats = {}
        for log in logs:
            camera_id_str = log.check_in_source or "unknown"
            if camera_id_str not in camera_stats:
                camera_stats[camera_id_str] = {"camera_id": camera_id_str, "count": 0, "late": 0, "early": 0}
            camera_stats[camera_id_str]["count"] += 1
            if log.is_late:
                camera_stats[camera_id_str]["late"] += 1
            if log.is_early_leave:
                camera_stats[camera_id_str]["early"] += 1

        return list(camera_stats.values())

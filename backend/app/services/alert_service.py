"""
Alert service — fires all PRD §5.3 security alerts:
  intruder, blacklist, after_hours, restricted_area, vip, loitering, spoof_attempt, unknown_person

Also handles occupancy counter incr/decr for PRD §5.2 / §5.4.
"""
import json, uuid
from datetime import datetime, timezone
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Alert
from ..config import settings
from .notification_service import NotificationService

_notifier = NotificationService()


SEVERITY = {
    "intruder": "high",
    "blacklist": "high",
    "spoof_attempt": "high",
    "restricted_area": "high",
    "suspicious_object": "medium",   # bag / suitcase / backpack near person
    "masked_face": "medium",
    "after_hours": "medium",
    "loitering": "medium",
    "vip": "low",
    "unknown_person": "low",
}


class AlertService:
    def __init__(self, db: AsyncSession, redis=None):
        self.db = db
        self.redis = redis

    async def fire(
        self,
        tenant_id: uuid.UUID,
        alert_type: str,
        message: str,
        employee_id: uuid.UUID | None = None,
        camera_id: uuid.UUID | None = None,
        snapshot_url: str | None = None,
        extra: dict | None = None,
    ) -> Alert:
        alert = Alert(
            tenant_id=tenant_id,
            alert_type=alert_type,
            severity=SEVERITY.get(alert_type, "medium"),
            employee_id=employee_id,
            camera_id=camera_id,
            snapshot_url=snapshot_url,
            message=message,
            extra=extra or {},
        )
        self.db.add(alert)
        await self.db.flush()

        payload = {
            "type": "alert",
            "alert_type": alert_type,
            "severity": alert.severity,
            "message": message,
            "employee_id": str(employee_id) if employee_id else None,
            "camera_id": str(camera_id) if camera_id else None,
            "snapshot_url": snapshot_url,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if self.redis:
            await self.redis.publish(f"alerts:{tenant_id}", json.dumps(payload))
            await self.redis.lpush(f"alerts:recent:{tenant_id}", json.dumps(payload))
            await self.redis.ltrim(f"alerts:recent:{tenant_id}", 0, 99)

        # Slack: VIP + blacklist (PRD §5.3)
        if alert_type in ("vip", "blacklist") and settings.SLACK_WEBHOOK_URL:
            await self._slack(message, alert_type)

        # Email: all high-severity alerts
        await self._notify_email(alert_type, message, employee_id, camera_id, snapshot_url)

        return alert

    async def _slack(self, message: str, alert_type: str):
        emoji = "🚨" if alert_type == "blacklist" else "⭐"
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                await c.post(settings.SLACK_WEBHOOK_URL,
                             json={"text": f"{emoji} *{alert_type.upper()}*: {message}"})
        except Exception:
            pass

    async def _notify_email(self, alert_type: str, message: str,
                            employee_id, camera_id, snapshot_url):
        """Send email for high-severity alerts if SMTP is configured."""
        cam_str = str(camera_id) if camera_id else "unknown"
        snap    = str(snapshot_url) if snapshot_url else None
        try:
            if alert_type == "spoof_attempt":
                await _notifier.notify_spoof(cam_str, snap)
            elif alert_type == "intruder":
                await _notifier.notify_intruder(cam_str, snap)
            elif alert_type == "blacklist":
                # employee name isn't available here — use the message which contains it
                await _notifier.notify_blacklist(message, cam_str, snap)
            elif alert_type == "after_hours":
                await _notifier.notify_after_hours(message, cam_str)
            # low-severity types (vip, unknown_person, loitering, restricted_area)
            # are not emailed — they already appear in the dashboard and Slack
        except Exception as e:
            import logging as _log
            _log.getLogger(__name__).warning("Email notification failed for %s: %s",
                                             alert_type, e)

    # ── Loitering ──────────────────────────────────────────────────────────
    async def check_loitering(
        self,
        tenant_id: uuid.UUID,
        employee_id: uuid.UUID,
        camera_id: uuid.UUID,
        employee_name: str,
        snapshot_url: str | None,
    ) -> bool:
        """Track dwell time per person per camera. Fire alert if > LOITERING_THRESHOLD_MIN."""
        if not self.redis:
            return False
        key = f"dwell:{tenant_id}:{employee_id}:{camera_id}"
        first = await self.redis.get(key)
        now = datetime.now(timezone.utc).timestamp()
        if first is None:
            await self.redis.setex(key, settings.LOITERING_THRESHOLD_MIN * 120, str(now))
            return False
        dwell_min = (now - float(first)) / 60
        if dwell_min >= settings.LOITERING_THRESHOLD_MIN:
            await self.redis.delete(key)
            await self.fire(
                tenant_id, "loitering",
                f"{employee_name} has been standing in the same area for over {int(dwell_min)} minutes. Please check if everything is okay.",
                employee_id=employee_id, camera_id=camera_id, snapshot_url=snapshot_url,
            )
            return True
        return False

    async def clear_loitering(self, tenant_id, employee_id, camera_id):
        """Call on check-out to reset the dwell timer."""
        if self.redis:
            key = f"dwell:{tenant_id}:{employee_id}:{camera_id}"
            await self.redis.delete(key)


class OccupancyService:
    """PRD §5.2 / §5.4: Redis-backed zone counters for live occupancy."""

    def __init__(self, redis):
        self.redis = redis

    def _zone_key(self, tenant_id, zone: str) -> str:
        return f"occ:{tenant_id}:{zone}"

    def _building_key(self, tenant_id) -> str:
        return f"occ:{tenant_id}:building"

    async def enter(self, tenant_id, zone: str):
        if not self.redis:
            return
        await self.redis.incr(self._zone_key(tenant_id, zone))
        await self.redis.incr(self._building_key(tenant_id))

    async def exit(self, tenant_id, zone: str):
        if not self.redis:
            return
        k = self._zone_key(tenant_id, zone)
        v = int(await self.redis.get(k) or 0)
        if v > 0:
            await self.redis.decr(k)
        bk = self._building_key(tenant_id)
        bv = int(await self.redis.get(bk) or 0)
        if bv > 0:
            await self.redis.decr(bk)

    async def get_building(self, tenant_id) -> int:
        if not self.redis:
            return 0
        return int(await self.redis.get(self._building_key(tenant_id)) or 0)

    async def get_zone(self, tenant_id, zone: str) -> int:
        if not self.redis:
            return 0
        return int(await self.redis.get(self._zone_key(tenant_id, zone)) or 0)

    async def get_all_zones(self, tenant_id) -> dict[str, int]:
        if not self.redis:
            return {}
        pattern = f"occ:{tenant_id}:*"
        keys = await self.redis.keys(pattern)
        out: dict[str, int] = {}
        for k in keys:
            zone = k.split(":")[-1]
            out[zone] = int(await self.redis.get(k) or 0)
        return out

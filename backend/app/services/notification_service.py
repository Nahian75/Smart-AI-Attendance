"""Outbound notifications: email, SMS, Slack/Teams, webhooks (stubs + hooks)."""
import httpx


class NotificationService:
    def __init__(self, webhook_urls: list[str] | None = None):
        self.webhook_urls = webhook_urls or []

    async def notify_late(self, employee_name: str, late_by_min: int):
        await self._fire_webhooks({
            "type": "late_arrival",
            "employee": employee_name,
            "late_by_min": late_by_min,
        })

    async def notify_spoof(self, camera_id: str):
        await self._fire_webhooks({"type": "spoof_attempt", "camera_id": camera_id})

    async def _fire_webhooks(self, payload: dict):
        async with httpx.AsyncClient(timeout=5) as client:
            for url in self.webhook_urls:
                try:
                    await client.post(url, json=payload)
                except Exception:
                    pass  # webhooks are best-effort; failures are logged elsewhere

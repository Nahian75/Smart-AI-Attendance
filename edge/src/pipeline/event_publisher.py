"""Publish recognition events to Redis pub/sub + POST to backend ingest API."""
import json
import os
import asyncio
import httpx
import redis.asyncio as aioredis
from ..utils.logger import get_logger

log = get_logger("publisher")


class EventPublisher:
    def __init__(self, redis_url: str, backend_url: str, tenant_id: str,
                 snapshot_dir: str = "/app/snapshots"):
        self.redis = aioredis.from_url(redis_url, decode_responses=True)
        self.backend_url = backend_url.rstrip("/")
        self.tenant_id = tenant_id
        self.snapshot_dir = snapshot_dir
        edge_token = os.getenv("EDGE_TOKEN", "")
        self._headers = {"Authorization": f"Bearer {edge_token}"} if edge_token else {}
        self._client = httpx.AsyncClient(timeout=5)

    def set_token(self, token: str) -> None:
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}

    async def _upload_snapshot(self, local_path: str) -> str | None:
        """Push the snapshot bytes to the backend so it lands under the
        backend's own SNAPSHOT_DIR — needed whenever the edge node doesn't
        share a filesystem with the backend (e.g. edge runs on-prem, backend
        runs in the cloud), since the raw local path is otherwise unreachable
        from wherever /snapshots gets served."""
        try:
            rel = os.path.relpath(local_path, self.snapshot_dir).replace(os.sep, "/")
            with open(local_path, "rb") as f:
                r = await self._client.post(
                    f"{self.backend_url}/api/v1/attendance/upload-snapshot",
                    headers=self._headers,
                    files={"file": (os.path.basename(local_path), f, "image/jpeg")},
                    data={"relative_path": rel},
                )
            if r.status_code == 200:
                return r.json().get("snapshot_url")
            log.error(f"snapshot upload HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e:
            log.error(f"snapshot upload failed: {e}")
        return None

    async def publish(self, event: dict):
        try:
            await self.redis.publish(f"attendance:{self.tenant_id}", json.dumps(event, default=str))
        except Exception as e:
            log.error(f"redis publish failed: {e}")

        event_type = event.get("type")
        if event_type in ("recognition", "unknown_person", "spoof_attempt"):
            try:
                snapshot_url = event.get("snapshot_url")
                if snapshot_url and os.path.isfile(snapshot_url):
                    snapshot_url = await self._upload_snapshot(snapshot_url)
                payload = {
                    "camera_id": event["camera_id"],
                    "employee_id": event.get("employee_id"),
                    "direction": event.get("direction"),
                    "track_id": event.get("track_id"),
                    "confidence": event.get("confidence", 0),
                    "is_live": event.get("is_live", True),
                    "spoof_score": event.get("spoof_score"),
                    "snapshot_url": snapshot_url,
                    "embedding_dist": event.get("embedding_dist"),
                }
                r = await self._client.post(
                    f"{self.backend_url}/api/v1/attendance/event",
                    params={"tenant_id": self.tenant_id},
                    headers=self._headers,
                    json=payload,
                )
                if r.status_code == 200:
                    result = r.json()
                    action = result.get("action", "?")
                    reason = result.get("reason", "")
                    emp = event.get("employee_id", "unknown")
                    if action == "skip":
                        log.warning(f"attendance skipped emp={emp} reason={reason} conf={event.get('confidence')}")
                    else:
                        log.info(f"attendance {action} emp={emp} conf={event.get('confidence')}")
                else:
                    log.error(f"backend ingest HTTP {r.status_code}: {r.text[:200]}")
            except Exception as e:
                log.error(f"backend ingest failed: {e}")

    async def close(self):
        await self._client.aclose()
        await self.redis.close()

import json
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import redis.asyncio as aioredis

from ...config import settings
from ...core.security import decode_token

router = APIRouter()


@router.websocket("/alerts/{tenant_id}")
async def alerts_ws(websocket: WebSocket, tenant_id: str, token: str = Query(...)):
    payload = decode_token(token)
    if not payload or payload.get("tenant_id") != tenant_id:
        await websocket.close(code=4401)
        return
    await websocket.accept()

    redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"alerts:{tenant_id}")

    async def _listen():
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                await websocket.send_text(msg["data"])

    async def _ping():
        while True:
            await asyncio.sleep(25)
            await websocket.send_text(json.dumps({"type": "ping"}))

    try:
        await asyncio.gather(_listen(), _ping())
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:
        pass
    finally:
        await pubsub.unsubscribe(f"alerts:{tenant_id}")
        await redis.close()


@router.websocket("/attendance/{tenant_id}")
async def attendance_ws(websocket: WebSocket, tenant_id: str, token: str = Query(...)):
    payload = decode_token(token)
    if not payload or payload.get("tenant_id") != tenant_id:
        await websocket.close(code=4401)
        return
    await websocket.accept()

    redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"attendance:{tenant_id}")

    async def _listen():
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                await websocket.send_text(msg["data"])

    async def _ping():
        """Send a keepalive ping every 25 s so proxies and browsers don't time out."""
        while True:
            await asyncio.sleep(25)
            await websocket.send_text(json.dumps({"type": "ping"}))

    try:
        await asyncio.gather(_listen(), _ping())
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:
        pass
    finally:
        await pubsub.unsubscribe(f"attendance:{tenant_id}")
        await redis.close()

"""MJPEG server using aiohttp so nginx can proxy it correctly."""
import asyncio
from aiohttp import web
from ..utils.logger import get_logger

log = get_logger("mjpeg")


_BOUNDARY = "frame"
_FRAME_HDR = (
    f"--{_BOUNDARY}\r\nContent-Type: image/jpeg\r\n\r\n"
).encode()
_FRAME_END = b"\r\n"


class MJPEGServer:
    def __init__(self, port: int = 8001):
        self.port = port
        self._frames: dict[str, bytes] = {}
        self._app = web.Application()
        self._app.router.add_get("/stream/{camera_id}", self._handle)
        self._runner: web.AppRunner | None = None

    def put_frame(self, camera_id: str, jpeg: bytes) -> None:
        self._frames[camera_id] = jpeg

    async def _handle(self, request: web.Request) -> web.StreamResponse:
        camera_id = request.match_info["camera_id"]
        resp = web.StreamResponse(
            headers={
                "Content-Type": f"multipart/x-mixed-replace; boundary={_BOUNDARY}",
                "Cache-Control": "no-cache, no-store",
                "Access-Control-Allow-Origin": "*",
            }
        )
        await resp.prepare(request)
        prev: bytes = b""
        try:
            while True:
                frame = self._frames.get(camera_id, b"")
                if frame and frame is not prev:
                    await resp.write(_FRAME_HDR + frame + _FRAME_END)
                    prev = frame
                else:
                    await asyncio.sleep(0.005)
        except (ConnectionError, ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
            pass
        return resp

    async def start(self) -> None:
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self.port)
        await site.start()
        log.info(f"MJPEG stream server on :{self.port}  ->  /stream/<camera_id>")

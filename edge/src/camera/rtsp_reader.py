"""Thread-based RTSP/ONVIF/file reader with auto-reconnect and frame skipping.

Robustness improvements over the naive cv2.VideoCapture loop:
- RTSP transport forced to TCP (avoids UDP packet loss causing silent drops)
- CAP_PROP_OPEN_TIMEOUT_MSEC / CAP_PROP_READ_TIMEOUT_MSEC prevent indefinite hangs
- Exponential backoff on reconnect (capped at 30 s) so a dead camera doesn't spam logs
- Consecutive-fail counter: if 10 reads fail in a row, force a full reconnect
- src_fps read from the actual stream (not hardcoded 30) for accurate frame-skip
"""
import threading
import time
import cv2
from typing import Callable
from ..utils.logger import get_logger

log = get_logger("rtsp")

_OPEN_TIMEOUT_MS  = 10_000   # max time to wait for VideoCapture.open()
_READ_TIMEOUT_MS  = 5_000    # max time to wait for a single frame
_MAX_CONSEC_FAILS = 10       # force reconnect after this many consecutive read failures
_MAX_BACKOFF_S    = 30       # cap on reconnect wait time


class RTSPReader:
    def __init__(self, camera_id: str, rtsp_url: str, fps_target: int = 6,
                 reconnect_delay: int = 3, use_gstreamer: bool = False):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.fps_target = fps_target
        self.reconnect_delay = reconnect_delay
        self.use_gstreamer = use_gstreamer
        self._cap = None
        self._running = False
        self._thread = None

    def _gst_pipeline(self) -> str:
        return (f"rtspsrc location={self.rtsp_url} latency=100 ! rtph264depay ! "
                "h264parse ! nvv4l2decoder ! nvvidconv ! video/x-raw,format=BGRx ! "
                "videoconvert ! video/x-raw,format=BGR ! appsink")

    def _source(self):
        url = self.rtsp_url.strip()
        if url.lstrip("-").isdigit():
            return int(url)
        return url

    def _connect(self) -> bool:
        try:
            if self.use_gstreamer:
                self._cap = cv2.VideoCapture(self._gst_pipeline(), cv2.CAP_GSTREAMER)
            if not self.use_gstreamer or not self._cap.isOpened():
                # Force TCP transport for RTSP — avoids silent UDP packet loss
                source = self._source()
                if isinstance(source, str) and source.startswith("rtsp://"):
                    # Force TCP — avoids UDP packet loss.
                    # Also set FFmpeg options for better H.264/H.265 compatibility.
                    source = source
                    self._cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
                    # Set RTSP transport to TCP via environment if not already done
                    import os as _os
                    _os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS",
                                           "rtsp_transport;tcp|analyzeduration;2000000|probesize;2000000")
                else:
                    self._cap = cv2.VideoCapture(source)
                self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                self._cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, _OPEN_TIMEOUT_MS)
                self._cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, _READ_TIMEOUT_MS)
                self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'H264'))
            if self._cap.isOpened():
                log.info(f"[{self.camera_id}] connected to {self.rtsp_url}")
                return True
        except Exception as e:
            log.error(f"[{self.camera_id}] connect error: {e}")
        if self._cap:
            self._cap.release()
        self._cap = None
        return False

    def start(self, on_frame: Callable):
        self._running = True
        self._thread = threading.Thread(target=self._loop, args=(on_frame,), daemon=True)
        self._thread.start()

    def _loop(self, on_frame: Callable):
        url = self.rtsp_url.strip()
        is_file = not (
            url.startswith("rtsp://") or url.startswith("http://")
            or url.startswith("https://") or url.lstrip("-").isdigit()
        )

        backoff = self.reconnect_delay
        n = 0
        consec_fails = 0

        while self._running:
            if self._cap is None or not self._cap.isOpened():
                if not self._connect():
                    log.warning(f"[{self.camera_id}] reconnect failed, waiting {backoff}s")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, _MAX_BACKOFF_S)
                    continue
                backoff = self.reconnect_delay  # reset on success

                # Read actual stream FPS for accurate frame-skip calculation
                src_fps = self._cap.get(cv2.CAP_PROP_FPS) or 30
                if src_fps <= 0 or src_fps > 120:
                    src_fps = 30
                skip = max(1, int(src_fps // max(1, self.fps_target))) if not is_file else 1
                consec_fails = 0

            ok, frame = self._cap.read()
            if not ok:
                consec_fails += 1
                if consec_fails >= _MAX_CONSEC_FAILS:
                    log.warning(
                        f"[{self.camera_id}] {consec_fails} consecutive read failures — reconnecting"
                    )
                    if self._cap:
                        self._cap.release()
                    self._cap = None
                    consec_fails = 0
                if is_file:
                    time.sleep(self.reconnect_delay)
                continue

            consec_fails = 0
            n += 1
            if n % skip == 0:
                on_frame(frame, time.time())
            if is_file:
                time.sleep(1.0 / self.fps_target)

    def stop(self):
        self._running = False
        if self._cap:
            self._cap.release()

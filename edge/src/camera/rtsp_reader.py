"""
RTSP reader — two-thread design for zero-accumulation live latency.

Problem with single-thread readers:
  Camera sends 25 fps. Inference takes ~200 ms = 5 fps capacity.
  In a single loop, the reader can only grab the next frame after inference
  finishes. Meanwhile FFmpeg's internal buffer fills with 20 frames/sec.
  After 30 seconds → 600 frames queued → 30-second delay on screen.

Solution — two threads:
  Thread 1 (capture):  reads from the camera as fast as possible.
                       Keeps ONLY the latest frame (overwrites every read).
                       Never blocks on inference. Buffer never grows.
  Thread 2 (dispatch): wakes at fps_target rate, grabs the latest frame,
                       calls on_frame(). Inference runs here (or is submitted
                       to an executor by the caller).

Result: the stream always shows a frame that is at most 1/fps_target seconds
old — regardless of how long inference takes.
"""
import os
import threading
import time
import cv2
from typing import Callable
from ..utils.logger import get_logger

# Guards the temporary OPENCV_FFMPEG_CAPTURE_OPTIONS override in _open_cap
# so parallel camera-connect threads don't clobber each other's env var.
_env_lock = threading.Lock()

log = get_logger("rtsp")

_OPEN_TIMEOUT_MS  = 20_000   # raised: H.265 DVR streams need 3-8s for codec init
_READ_TIMEOUT_MS  = 8_000
_MAX_CONSEC_FAILS = 10
_MAX_BACKOFF_S    = 30

# Set FFmpeg options ONCE at module load — not per-connection.
# Per-connection writes to a process-wide env var create race conditions when
# multiple cameras connect in parallel threads (each thread overwrites the other).
#
# fflags;nobuffer is intentionally excluded:
#   H.265 / HEVC needs a short read-ahead to locate VPS/SPS/PPS headers before
#   the decoder can initialise. nobuffer prevents this and makes Hikvision DVR
#   streams fail to open or return green/corrupted frames.
#
# analyzeduration / probesize at 5 MB:
#   DVR streams have longer GOPs and larger codec headers than direct-IP cameras.
#   3 MB was still too low for some Hikvision NVR models; 5 MB is safe for all.
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    # fflags;nobuffer is absent — H.265 needs to buffer VPS/SPS/PPS on connect.
    "rtsp_transport;tcp"
    "|analyzeduration;5000000"
    "|probesize;5000000",
)


class RTSPReader:
    def __init__(self, camera_id: str, rtsp_url: str, fps_target: int = 0,
                 reconnect_delay: int = 3, use_gstreamer: bool = False):
        self.camera_id    = camera_id
        self.rtsp_url     = rtsp_url
        # 0 = auto-detect from stream on first connect
        self._fps_target_override = max(0, fps_target)
        self.fps_target   = self._fps_target_override or 6  # sensible default until connected
        self.reconnect_delay = reconnect_delay
        self.use_gstreamer   = use_gstreamer

        self._cap     = None
        self._running = False

        # Shared latest-frame slot — written by capture thread, read by dispatch thread
        self._latest_frame: cv2.typing.MatLike | None = None
        self._latest_ts:    float = 0.0
        self._frame_lock    = threading.Lock()

        # Reconnect signalling from capture thread → dispatch thread
        self._need_reconnect = threading.Event()

        self._capture_thread:  threading.Thread | None = None
        self._dispatch_thread: threading.Thread | None = None

    # ── Public API ────────────────────────────────────────────────────────────
    def start(self, on_frame: Callable) -> None:
        self._running = True
        self._dispatch_thread = threading.Thread(
            target=self._dispatch_loop, args=(on_frame,), daemon=True,
            name=f"dispatch-{self.camera_id}",
        )
        self._dispatch_thread.start()

    def stop(self) -> None:
        self._running = False
        if self._cap:
            self._cap.release()
            self._cap = None

    # ── Capture thread — reads at full camera speed ───────────────────────────
    def _capture_loop(self) -> None:
        """
        Reads frames as fast as the camera / network allows.
        Only stores the latest frame — old frames are silently overwritten.
        Signals _need_reconnect on persistent failure.
        """
        consec_fails = 0
        while self._running:
            if self._cap is None or not self._cap.isOpened():
                time.sleep(0.05)
                continue

            ok, frame = self._cap.read()
            if ok:
                with self._frame_lock:
                    self._latest_frame = frame
                    self._latest_ts    = time.time()
                consec_fails = 0
            else:
                consec_fails += 1
                if consec_fails >= _MAX_CONSEC_FAILS:
                    log.warning("[%s] %d consecutive read failures — reconnecting",
                                self.camera_id, consec_fails)
                    if self._cap:
                        self._cap.release()
                    self._cap = None
                    consec_fails = 0
                    self._need_reconnect.set()

    # ── Dispatch thread — delivers at fps_target rate ─────────────────────────
    def _dispatch_loop(self, on_frame: Callable) -> None:
        """
        Connects the camera, starts the capture thread, then wakes at
        fps_target rate and delivers the latest available frame to on_frame().
        """
        backoff = self.reconnect_delay

        # Initial connect
        while self._running and not self._connect():
            log.warning("[%s] connect failed, retrying in %ds", self.camera_id, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF_S)
        if not self._running:
            return
        backoff = self.reconnect_delay
        # Read interval AFTER connect so auto-detected fps_target is used.
        interval = 1.0 / self.fps_target

        # Start capture thread
        self._capture_thread = threading.Thread(
            target=self._capture_loop, daemon=True,
            name=f"capture-{self.camera_id}",
        )
        self._capture_thread.start()
        log.info("[%s] started (fps_target=%d)", self.camera_id, self.fps_target)

        last_dispatch = 0.0

        while self._running:
            # ── Reconnect if capture thread signalled failure ─────────────
            if self._need_reconnect.is_set():
                self._need_reconnect.clear()
                with self._frame_lock:
                    self._latest_frame = None
                while self._running and not self._connect():
                    log.warning("[%s] reconnect failed, retrying in %ds",
                                self.camera_id, backoff)
                    time.sleep(backoff)
                    backoff = min(backoff * 2, _MAX_BACKOFF_S)
                backoff = self.reconnect_delay
                interval = 1.0 / self.fps_target  # refresh in case auto-FPS changed
                continue

            # ── Dispatch latest frame at fps_target rate ──────────────────
            now = time.time()
            wait = interval - (now - last_dispatch)
            if wait > 0:
                time.sleep(wait)

            with self._frame_lock:
                frame = self._latest_frame
                ts    = self._latest_ts

            if frame is not None and ts > last_dispatch:
                last_dispatch = ts
                on_frame(frame, ts)

    # ── Camera connect ────────────────────────────────────────────────────────
    def _connect(self) -> bool:
        try:
            if self.use_gstreamer:
                pipeline = (
                    f"rtspsrc location={self.rtsp_url} latency=0 ! rtph264depay ! "
                    "h264parse ! nvv4l2decoder ! nvvidconv ! "
                    "video/x-raw,format=BGRx ! videoconvert ! "
                    "video/x-raw,format=BGR ! appsink drop=true max-buffers=1"
                )
                cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
                if cap.isOpened():
                    self._cap = cap
                    log.info("[%s] connected via GStreamer", self.camera_id)
                    return True

            url = self.rtsp_url.strip()
            src = int(url) if url.lstrip("-").isdigit() else url

            cap = self._open_cap(src)
            if cap is None:
                return False

            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 0

            # Reject 0×0 streams — FFmpeg opened the TCP connection but could
            # not parse the codec headers (H.265+, encrypted, wrong URL, etc.).
            # Without this check the reader would "connect" but never get frames.
            if w == 0 or h == 0:
                log.warning("[%s] stream opened but resolution is 0×0 — codec unreadable, rejecting",
                            self.camera_id)
                cap.release()
                return False

            if self._fps_target_override:
                self.fps_target = self._fps_target_override
            elif fps > 0 and fps < 200:
                self.fps_target = max(4, min(10, round(fps / 3)))
                log.info("[%s] fps_target auto-set to %d (native=%.0f, ratio=1:3)",
                         self.camera_id, self.fps_target, fps)
            else:
                self.fps_target = 6

            log.info("[%s] connected — %dx%d @ %.0f fps (processing at %d fps)",
                     self.camera_id, w, h, fps, self.fps_target)
            self._cap = cap
            with self._frame_lock:
                self._latest_frame = None
            return True

        except Exception as e:
            log.error("[%s] connect error: %s", self.camera_id, e)

        if self._cap:
            self._cap.release()
        self._cap = None
        return False

    def _open_cap(self, src) -> cv2.VideoCapture | None:
        """Open a VideoCapture with timeout params; try UDP fallback for RTSP."""
        is_rtsp = isinstance(src, str) and src.startswith("rtsp://")

        def _try(extra_opts: str = "") -> cv2.VideoCapture | None:
            if is_rtsp and extra_opts:
                with _env_lock:
                    original = os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS", "")
                    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = extra_opts
                    cap = cv2.VideoCapture(src, cv2.CAP_FFMPEG)
                    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = original
            elif is_rtsp:
                cap = cv2.VideoCapture(src, cv2.CAP_FFMPEG)
            else:
                cap = cv2.VideoCapture(src)

            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, _OPEN_TIMEOUT_MS)
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC,  _READ_TIMEOUT_MS)

            if not cap.isOpened():
                cap.release()
                return None

            # Don't probe frames here — the 5-frame probe consumed the DVR's
            # initial burst, leaving the capture thread with an empty buffer.
            # _try_rtsp already has a first_frame.wait(timeout=25) gate that
            # correctly validates the connection once the capture thread is live.
            return cap

        # Attempt 1: TCP with standard options
        cap = _try()
        if cap is not None:
            return cap

        if is_rtsp:
            # Attempt 2: UDP — some Hikvision DVR models refuse TCP negotiation
            log.warning("[%s] TCP connect failed — retrying with UDP", self.camera_id)
            cap = _try(
                "rtsp_transport;udp"
                "|analyzeduration;5000000"
                "|probesize;5000000"
            )
            if cap is not None:
                return cap

            # Attempt 3: TCP with strict=-2 (H.265+ lenient mode).
            log.warning(
                "[%s] UDP also failed — retrying with H.265+ lenient mode (Hikvision DVR)",
                self.camera_id,
            )
            cap = _try(
                "rtsp_transport;tcp"
                "|strict;-2"
                "|analyzeduration;5000000"
                "|probesize;5000000"
            )
            if cap is not None:
                return cap

            # Attempt 4: force output pixel format — last-resort for chroma issues.
            log.warning("[%s] H.265+ lenient failed — retrying with forced pixel format",
                        self.camera_id)
            cap = _try(
                "rtsp_transport;tcp"
                "|strict;-2"
                "|pix_fmt;bgr24"
                "|analyzeduration;5000000"
                "|probesize;5000000"
            )
            if cap is not None:
                return cap

            log.error(
                "[%s] all connection attempts failed.\n"
                "  For Hikvision DVR streams, try:\n"
                "  1. Verify H.264 is saved (not H.265/H.265+) in DVR encoding settings\n"
                "  2. Set Frame Rate to 15 or 25 (not 10) — some models need higher FPS\n"
                "  3. Use sub-stream URL: /Streaming/Channels/102 (usually H.264)\n"
                "  4. Restart the DVR fully to apply encoding changes",
                self.camera_id,
            )

        return None

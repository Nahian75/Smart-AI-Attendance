"""
Universal camera reader — works with any IP camera or DVR from any brand.

Connection strategy (tried in order, first success wins):

  1. ONVIF → RTSP  — Discover H.264 stream URI via ONVIF standard protocol,
                      then stream via RTSPReader/FFmpeg. Fixes DVRs that output
                      H.265+ on the main RTSP port but expose clean H.264 via
                      ONVIF (Hikvision, Dahua, Axis, Reolink, Amcrest, etc.)

  2. RTSP direct   — Standard RTSP/FFmpeg with automatic TCP/UDP/strict fallbacks.
                      Works for 90%+ of cameras immediately.

  3. HCNetSDK      — Hikvision official SDK. Handles H.265+ natively.
                      Activates when edge/sdk/hikvision/libhcnetsdk.so exists.

  4. Dahua NetSDK  — Same for Dahua, Amcrest, Lorex, ANNKE, Swann.
                      Activates when edge/sdk/dahua/libdhnetsdk.so exists.

All methods share a single on_frame(bgr, timestamp) callback so the rest of
the pipeline (YOLO, ArcFace, MJPEG) needs zero changes.
"""

import re
import time
import logging
import threading
from urllib.parse import urlparse
from typing import Callable

log = logging.getLogger(__name__)


def _parse_url(rtsp_url: str) -> dict:
    try:
        p = urlparse(rtsp_url.strip())
        channel = 1
        m = re.search(r"/(\d+)$", p.path)
        if m:
            num = int(m.group(1))
            channel = num // 100 if num >= 100 else num
        return {
            "host":     p.hostname or "",
            "port":     p.port or 554,
            "username": p.username or "admin",
            "password": p.password or "",
            "channel":  max(1, channel),
        }
    except Exception:
        return {"host": "", "port": 554, "username": "admin",
                "password": "", "channel": 1}


def _is_hikvision_url(rtsp_url: str) -> bool:
    url = (rtsp_url or "").lower()
    return any(k in url for k in ("streaming/channels", "hikvision", "/isapi"))


def _is_dahua_url(rtsp_url: str) -> bool:
    url = (rtsp_url or "").lower()
    return any(k in url for k in ("realmonitor", "dahua", "amcrest"))


class UniversalCameraReader:
    """
    Drop-in replacement for RTSPReader.  Tries ONVIF → RTSP → HCNetSDK →
    DahuaSDK in order and reconnects automatically when a stream drops.

    Interface is identical to RTSPReader:
        reader = UniversalCameraReader(camera_id, rtsp_url, fps_target=8)
        reader.start(on_frame)   # non-blocking
        reader.stop()
    """

    def __init__(self, camera_id: str, rtsp_url: str,
                 fps_target: int = 0,
                 reconnect_delay: int = 3,
                 use_gstreamer: bool = False):
        self.camera_id       = camera_id
        self.rtsp_url        = rtsp_url
        self.fps_target      = fps_target
        self.reconnect_delay = reconnect_delay
        self.use_gstreamer   = use_gstreamer

        self._on_frame:   Callable | None = None
        self._running     = False
        self._inner:      object | None = None  # active RTSPReader or SDK capture
        self._loop_thread: threading.Thread | None = None
        self._params = _parse_url(rtsp_url)

        # Mirror RTSPReader's public attribute so heartbeat_loop works
        self._dispatch_thread: threading.Thread | None = None

        # Track SDK failure so we skip it on reconnects and go straight to RTSP.
        # SDK attempt takes 15s and leaves the DVR slot busy for several seconds
        # after logout, causing subsequent RTSP connections to get 0×0 resolution.
        # Once RTSP is known to work, SDK is never retried for this camera.
        self._sdk_works: bool | None = None   # None=untried, True=works, False=failed

    # ── Public API (same as RTSPReader) ──────────────────────────────────────

    def start(self, on_frame: Callable) -> None:
        self._on_frame = on_frame
        self._running  = True
        self._loop_thread = threading.Thread(
            target=self._outer_loop, daemon=True,
            name=f"univ-{self.camera_id}",
        )
        self._loop_thread.start()
        # Expose as _dispatch_thread so existing code that checks it still works
        self._dispatch_thread = self._loop_thread

    def stop(self) -> None:
        self._running = False
        self._stop_inner()

    # ── Outer reconnect loop ──────────────────────────────────────────────────

    def _outer_loop(self) -> None:
        backoff = self.reconnect_delay
        while self._running:
            connected = self._try_all_methods()
            if connected:
                backoff = self.reconnect_delay
                # Block until the inner reader dies naturally
                self._wait_for_inner()
                if self._running:
                    log.warning("[%s] stream lost — reconnecting in %ds",
                                self.camera_id, backoff)
            else:
                log.warning("[%s] all connection methods failed — retrying in %ds",
                            self.camera_id, backoff)

            if self._running:
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)
            self._stop_inner()

    def _wait_for_inner(self) -> None:
        """Block until the inner reader's dispatch thread or decode loop dies."""
        inner = self._inner
        if inner is None:
            return
        # RTSPReader: wait for dispatch thread
        dt = getattr(inner, "_dispatch_thread", None)
        if dt and hasattr(dt, "is_alive"):
            while self._running and dt.is_alive():
                time.sleep(1)
            return
        # SDK readers (HikvisionSDKCapture / DahuaSDKCapture):
        # use _stream_alive event if available (set by decode loop, cleared on exit)
        alive_evt = getattr(inner, "_stream_alive", None)
        if alive_evt is not None:
            while self._running and alive_evt.is_set():
                time.sleep(1)
            return
        # Fallback: poll _running flag
        while self._running and getattr(inner, "_running", False):
            time.sleep(1)

    def _stop_inner(self) -> None:
        inner = self._inner
        self._inner = None
        if inner is not None:
            try:
                inner.stop()
            except Exception:
                pass

    # ── Connection attempts ───────────────────────────────────────────────────

    def _try_all_methods(self) -> bool:
        # ── 0. Vendor SDK FIRST when available ───────────────────────────────
        # Only try SDK if it hasn't already failed for this camera.  When SDK
        # fails (no first frame in 15s), it leaves the DVR slot busy for
        # several seconds after logout, causing RTSP to get 0×0 resolution on
        # the very next attempt.  Once we know SDK fails, skip it so RTSP
        # connects cleanly without the DVR slot interference.
        if _is_hikvision_url(self.rtsp_url) and self._hikvision_sdk_available() \
                and self._sdk_works is not False:
            log.info("[%s] Hikvision URL + HCNetSDK present — using SDK first",
                     self.camera_id)
            if self._try_hikvision_sdk():
                self._sdk_works = True
                return True
            else:
                self._sdk_works = False
                log.info("[%s] SDK failed — skipping SDK on future reconnects, using RTSP",
                         self.camera_id)
                # Brief pause so the DVR releases the slot before RTSP tries.
                time.sleep(5)

        if _is_dahua_url(self.rtsp_url) and self._dahua_sdk_available() \
                and self._sdk_works is not False:
            log.info("[%s] Dahua URL + NetSDK present — using SDK first",
                     self.camera_id)
            if self._try_dahua_sdk():
                self._sdk_works = True
                return True
            else:
                self._sdk_works = False
                time.sleep(5)

        # ── 1. ONVIF → RTSP ──────────────────────────────────────────────────
        # Always try ONVIF after SDK fails — the resolver prefers H.264 profiles,
        # which avoids H.265+ main streams that FFmpeg can't decode even when
        # the SDK or VLC handle them fine. This is the fix for Hikvision DVRs
        # where channel N main stream is H.265+ but the ONVIF sub-stream is H.264.
        onvif_url = self._resolve_onvif()
        if onvif_url:
            log.info("[%s] ONVIF URI resolved — trying RTSP", self.camera_id)
            if self._try_rtsp(onvif_url):
                return True

        # ── 2. RTSP direct ───────────────────────────────────────────────────
        if self._try_rtsp(self.rtsp_url):
            return True

        # ── 3. Vendor SDK fallback (if not already tried above) ───────────────
        if not _is_hikvision_url(self.rtsp_url) and self._try_hikvision_sdk():
            return True
        if not _is_dahua_url(self.rtsp_url) and self._try_dahua_sdk():
            return True

        return False

    @staticmethod
    def _hikvision_sdk_available() -> bool:
        try:
            from .hikvision_sdk import HikvisionSDKCapture
            return HikvisionSDKCapture.is_available()
        except Exception:
            return False

    @staticmethod
    def _dahua_sdk_available() -> bool:
        try:
            from .dahua_sdk import DahuaSDKCapture
            return DahuaSDKCapture.is_available()
        except Exception:
            return False

    def _try_rtsp(self, url: str) -> bool:
        """
        Start an RTSPReader and wait up to 25 s for the first frame.
        This is the only correct way to use RTSPReader — calling .start()
        and letting it manage its own threads avoids the double-connect bug.
        """
        from .rtsp_reader import RTSPReader

        first_frame = threading.Event()

        def _cb(frame, ts):
            first_frame.set()           # signal connection confirmed
            if self._on_frame:
                self._on_frame(frame, ts)

        reader = RTSPReader(
            self.camera_id, url,
            fps_target=self.fps_target,
            reconnect_delay=self.reconnect_delay,
            use_gstreamer=self.use_gstreamer,
        )
        reader.start(_cb)

        # Wait for first real frame (confirms successful decode, not just TCP open)
        if first_frame.wait(timeout=25):
            self._inner = reader
            log.info("[%s] RTSP connected: %s", self.camera_id,
                     re.sub(r":[^@]+@", ":***@", url))
            return True

        log.debug("[%s] RTSP timed out: %s", self.camera_id,
                  re.sub(r":[^@]+@", ":***@", url))
        reader.stop()
        return False

    def _resolve_onvif(self) -> str | None:
        try:
            from .onvif_resolver import resolve_best_stream
            return resolve_best_stream(self.rtsp_url, prefer_h264=True)
        except Exception as e:
            log.debug("[%s] ONVIF: %s", self.camera_id, e)
            return None

    def _try_hikvision_sdk(self) -> bool:
        try:
            from .hikvision_sdk import HikvisionSDKCapture
            if not HikvisionSDKCapture.is_available():
                return False
            p = self._params

            # Wait for the first real decoded frame before declaring success.
            # cap.start() returns True on SDK login + preview start, but frames
            # only flow once PyAV decodes the first chunk from the callback.
            # Without this gate, RTSP fallback never runs on cameras where the
            # SDK connects but the data callback is never fired.
            first_frame = threading.Event()

            def _on_frame_tracked(frame, ts):
                first_frame.set()
                if self._on_frame:
                    self._on_frame(frame, ts)

            cap = HikvisionSDKCapture(
                host=p["host"], port=8000,
                username=p["username"], password=p["password"],
                channel=p["channel"],
            )
            if not cap.start(_on_frame_tracked):
                return False

            if first_frame.wait(timeout=15):
                self._inner = cap
                log.info("[%s] connected via Hikvision HCNetSDK", self.camera_id)
                return True

            log.debug("[%s] HCNetSDK: no frames in 15s — falling back", self.camera_id)
            cap.stop()
        except Exception as e:
            log.debug("[%s] HCNetSDK: %s", self.camera_id, e)
        return False

    def _try_dahua_sdk(self) -> bool:
        try:
            from .dahua_sdk import DahuaSDKCapture
            if not DahuaSDKCapture.is_available():
                return False
            p = self._params

            first_frame = threading.Event()

            def _on_frame_tracked(frame, ts):
                first_frame.set()
                if self._on_frame:
                    self._on_frame(frame, ts)

            cap = DahuaSDKCapture(
                host=p["host"], port=37777,
                username=p["username"], password=p["password"],
                channel=p["channel"],
            )
            if not cap.start(_on_frame_tracked):
                return False

            if first_frame.wait(timeout=15):
                self._inner = cap
                log.info("[%s] connected via Dahua NetSDK", self.camera_id)
                return True

            log.debug("[%s] DahuaSDK: no frames in 15s — falling back", self.camera_id)
            cap.stop()
        except Exception as e:
            log.debug("[%s] DahuaSDK: %s", self.camera_id, e)
        return False

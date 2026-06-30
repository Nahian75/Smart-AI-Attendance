"""
Hikvision HCNetSDK capture — native decoding of H.265+ and all proprietary streams.

The SDK is Hikvision's official C library. It handles every codec and encryption
variant their devices produce, including H.265+ (non-standard VPS/SPS/PPS) that
breaks FFmpeg.

Download (free, registration required):
  https://www.hikvision.com/en/support/download/sdk/
  → "Device Network SDK for Linux 64-bit"

Place the extracted .so files in:
  edge/sdk/hikvision/
    libhcnetsdk.so
    libHCCore.so
    libhpr.so
    libcrypto.so.1.1   (may already exist on system)
    libssl.so.1.1      (may already exist on system)
    libStreamPlay.so
    libPlayCtrl.so     (optional — needed for hardware decode path)

The capture runs in a background thread and delivers BGR numpy frames
at the same interface as RTSPReader (on_frame callback).
"""

import os
import ctypes
import ctypes.util
import threading
import logging
import time
import queue
from typing import Callable

import numpy as np
import cv2

log = logging.getLogger(__name__)

# ── SDK search paths ──────────────────────────────────────────────────────────
_SDK_DIRS = [
    "/app/sdk/hikvision",
    "/opt/hikvision/lib",
    "/usr/local/lib/hikvision",
]
_SDK_LIB = "libhcnetsdk.so"

# ── SDK constants ─────────────────────────────────────────────────────────────
NET_DVR_SYSHEAD      = 1
NET_DVR_STREAMDATA   = 2
NET_DVR_RTP_OR_RTSP  = 112   # real-time stream via RTSP negotiated by SDK
NET_DVR_NOERROR      = 0
LOGIN_HANDLE_INVALID = -1

# ── SDK structures ────────────────────────────────────────────────────────────

class NET_DVR_USER_LOGIN_INFO(ctypes.Structure):
    _fields_ = [
        ("sDeviceAddress", ctypes.c_char * 129),
        ("byUseTransport", ctypes.c_ubyte),
        ("wPort",          ctypes.c_uint16),
        ("sUserName",      ctypes.c_char * 64),
        ("sPassword",      ctypes.c_char * 64),
        ("cbLoginResult",  ctypes.c_void_p),
        ("pUser",          ctypes.c_void_p),
        ("bUseAsynLogin",  ctypes.c_int),
        ("byRes3",         ctypes.c_char * 100),
    ]


class NET_DVR_DEVICEINFO_V40(ctypes.Structure):
    _fields_ = [
        ("struDeviceV30",  ctypes.c_char * 312),   # NET_DVR_DEVICEINFO_V30
        ("bySupportLock",  ctypes.c_ubyte),
        ("byRetryLoginTime", ctypes.c_ubyte),
        ("byPasswordLevel",  ctypes.c_ubyte),
        ("byRes1",         ctypes.c_ubyte),
        ("dwSurplusLockTime", ctypes.c_uint32),
        ("byHighDef",      ctypes.c_ubyte),
        ("bySupportProFileEx", ctypes.c_ubyte),
        ("byRes2",         ctypes.c_char * 242),
    ]


class NET_DVR_PREVIEWINFO(ctypes.Structure):
    _fields_ = [
        ("lChannel",       ctypes.c_long),
        ("dwStreamType",   ctypes.c_uint32),   # 0=main, 1=sub, 2=third
        ("dwLinkMode",     ctypes.c_uint32),   # 0=TCP, 1=UDP, 2=multicast
        ("hPlayWnd",       ctypes.c_void_p),
        ("bBlocked",       ctypes.c_int),
        ("bPassbackRecord", ctypes.c_int),
        ("byPreviewMode",  ctypes.c_ubyte),
        ("byRes1",         ctypes.c_char * 3),
        ("byVideoCodingType", ctypes.c_ubyte),
        ("byRes2",         ctypes.c_char * 215),
        ("byRes3",         ctypes.c_char * 16),
    ]


# Callback signature: (lRealHandle, dwDataType, pBuffer, dwBufSize, pUser)
REALDATACALLBACK = ctypes.CFUNCTYPE(
    None,
    ctypes.c_long,
    ctypes.c_uint32,
    ctypes.POINTER(ctypes.c_ubyte),
    ctypes.c_uint32,
    ctypes.c_void_p,
)


_sdk_initialized = False   # NET_DVR_Init must only be called once per process
_sdk_init_lock   = threading.Lock()


def _find_sdk_lib() -> str | None:
    for d in _SDK_DIRS:
        path = os.path.join(d, _SDK_LIB)
        if os.path.exists(path):
            return path
    found = ctypes.util.find_library("hcnetsdk")
    return found


class HikvisionSDKCapture:
    """
    Frame capture using Hikvision HCNetSDK.

    Handles H.265+, H.264+, and all proprietary Hikvision codecs.
    Delivers decoded BGR frames to the on_frame(frame, timestamp) callback.
    """

    def __init__(self, host: str, port: int, username: str, password: str,
                 channel: int = 1, stream_type: int = 0):
        self.host        = host
        self.port        = port
        self.username    = username
        self.password    = password
        self.channel     = channel      # 1-based DVR channel number
        self.stream_type = stream_type  # 0=main, 1=sub

        self._sdk:         ctypes.CDLL | None = None
        self._user_id:     int = LOGIN_HANDLE_INVALID
        self._real_handle: int = -1
        self._running    = False
        self._thread:    threading.Thread | None = None
        self._on_frame:  Callable | None = None

        # Internal queue: raw H.264/H.265 chunks from SDK callback.
        # maxsize=4 keeps at most one keyframe + a few P-frames buffered.
        # Older chunks are discarded to maintain low latency.
        self._chunk_q: queue.Queue[bytes] = queue.Queue(maxsize=4)
        self._stream_alive = threading.Event()  # set while decode loop runs
        # Keep a reference to the ctypes callback to prevent GC
        self._cb_ref: REALDATACALLBACK | None = None

        self._sdk = self._load_sdk()

    # ── Public API ────────────────────────────────────────────────────────────

    @classmethod
    def is_available(cls) -> bool:
        """Return True if the HCNetSDK library is installed."""
        return _find_sdk_lib() is not None

    def start(self, on_frame: Callable) -> bool:
        """
        Login to the DVR, open the real-time stream, start delivering frames.
        Returns True on success, False if SDK not available or login fails.
        """
        if self._sdk is None:
            return False
        self._on_frame = on_frame
        self._running  = True

        if not self._login():
            self._running = False
            return False

        if not self._start_preview():
            self._logout()
            self._running = False
            return False

        self._thread = threading.Thread(
            target=self._decode_loop, daemon=True,
            name=f"hksdk-decode-{self.host}-ch{self.channel}",
        )
        self._thread.start()
        log.info("[HikvisionSDK] streaming %s:%d ch%d", self.host, self.port, self.channel)
        return True

    def stop(self) -> None:
        self._running = False
        if self._real_handle >= 0:
            try:
                self._sdk.NET_DVR_StopRealPlay(self._real_handle)
            except Exception:
                pass
            self._real_handle = -1
        self._logout()

    # ── SDK internals ─────────────────────────────────────────────────────────

    def _load_sdk(self) -> ctypes.CDLL | None:
        lib_path = _find_sdk_lib()
        if not lib_path:
            log.debug("HikvisionSDK: library not found in %s", _SDK_DIRS)
            return None
        try:
            global _sdk_initialized
            lib_dir = os.path.dirname(lib_path)
            dep_dirs = [lib_dir, os.path.join(lib_dir, "HCNetSDKCom")]
            dep_names = [
                "libcrypto.so", "libssl.so", "libhpr.so",
                "libiconv2.so", "libHCCore.so",
                "libStreamTransClient.so", "libSystemTransform.so",
                "libHCGeneralCfgMgr.so", "libHCPreview.so",
                "libHCPlayBack.so", "libHCAlarm.so",
                "libStreamPlay.so", "libPlayCtrl.so",
            ]
            for dep in dep_names:
                for d in dep_dirs:
                    dep_path = os.path.join(d, dep)
                    if os.path.exists(dep_path):
                        try:
                            ctypes.CDLL(dep_path, mode=ctypes.RTLD_GLOBAL)
                        except Exception:
                            pass
                        break

            sdk = ctypes.CDLL(lib_path, mode=ctypes.RTLD_GLOBAL)

            with _sdk_init_lock:
                global _sdk_initialized
                if not _sdk_initialized:
                    sdk.NET_DVR_Init()
                    sdk.NET_DVR_SetConnectTime(2000, 1)
                    sdk.NET_DVR_SetReconnect(0, False)
                    _sdk_initialized = True
                    log.info("HikvisionSDK loaded and initialised: %s", lib_path)
                else:
                    log.info("HikvisionSDK loaded (already initialised): %s", lib_path)
            return sdk
        except Exception as e:
            log.warning("HikvisionSDK load failed: %s", e)
            return None

    def _login(self) -> bool:
        info = NET_DVR_USER_LOGIN_INFO()
        info.sDeviceAddress = self.host.encode()
        info.wPort          = self.port
        info.sUserName      = self.username.encode()
        info.sPassword      = self.password.encode()
        info.bUseAsynLogin  = 0  # synchronous login

        dev_info = NET_DVR_DEVICEINFO_V40()

        # SDK LONG = 32-bit int on Linux — must use c_int, not c_long (64-bit).
        # c_long would read -1 (0xFFFFFFFF) as 4294967295, masking login failures.
        self._sdk.NET_DVR_Login_V40.restype = ctypes.c_int
        uid = self._sdk.NET_DVR_Login_V40(
            ctypes.byref(info), ctypes.byref(dev_info)
        )
        if uid < 0:
            err = self._sdk.NET_DVR_GetLastError()
            log.warning("HikvisionSDK login failed: err=%d host=%s", err, self.host)
            return False
        self._user_id = uid
        log.info("HikvisionSDK logged in uid=%d host=%s", uid, self.host)
        return True

    def _start_preview(self) -> bool:
        preview = NET_DVR_PREVIEWINFO()
        preview.lChannel     = self.channel
        preview.dwStreamType = self.stream_type
        preview.dwLinkMode   = 0   # TCP
        preview.bBlocked     = 0   # non-blocking

        def _raw_cb(handle, data_type, buf, buf_size, user):
            if not self._running:
                return
            if data_type in (NET_DVR_SYSHEAD, NET_DVR_STREAMDATA, NET_DVR_RTP_OR_RTSP):
                raw = bytes(buf[:buf_size])
                # Drop the OLDEST chunk when full to maintain low latency.
                # If we dropped the new chunk (put_nowait) the decoder would
                # starve of fresh data and lag behind the live stream.
                if self._chunk_q.full():
                    try:
                        self._chunk_q.get_nowait()
                    except queue.Empty:
                        pass
                try:
                    self._chunk_q.put_nowait(raw)
                except queue.Full:
                    pass

        self._cb_ref = REALDATACALLBACK(_raw_cb)

        self._sdk.NET_DVR_RealPlay_V40.restype = ctypes.c_int
        handle = self._sdk.NET_DVR_RealPlay_V40(
            self._user_id,
            ctypes.byref(preview),
            self._cb_ref,
            None,
        )
        if handle < 0:
            err = self._sdk.NET_DVR_GetLastError()
            log.warning("HikvisionSDK preview start failed: err=%d", err)
            return False
        self._real_handle = handle
        return True

    def _logout(self) -> None:
        if self._user_id >= 0:
            try:
                self._sdk.NET_DVR_Logout(self._user_id)
            except Exception:
                pass
            self._user_id = LOGIN_HANDLE_INVALID

    def _decode_loop(self) -> None:
        """
        Consume raw H.264/H.265 chunks from the SDK callback and decode them
        to BGR frames using PyAV (libavcodec). Delivers to on_frame().
        """
        self._stream_alive.set()
        try:
            import av
        except ImportError:
            log.error("HikvisionSDK: 'av' (PyAV) package required. pip install av")
            self._running = False
            self._stream_alive.clear()
            return

        codec_ctx = None
        codec_name = None
        consecutive_errors = 0

        while self._running:
            try:
                chunk = self._chunk_q.get(timeout=3.0)
            except queue.Empty:
                consecutive_errors += 1
                if consecutive_errors >= 10:
                    log.warning("[HikvisionSDK] %s ch%d: no data for 30s — stream lost",
                                self.host, self.channel)
                    break
                continue
            consecutive_errors = 0

            # Auto-detect codec from first bytes (H.264 vs H.265 start codes).
            # Annex B format: 0x00 0x00 0x00 0x01 <NAL header>
            if codec_ctx is None:
                if len(chunk) >= 5:
                    b = chunk[4]
                    nal_type_h265 = (b >> 1) & 0x3F
                    codec_name = "hevc" if nal_type_h265 in (32, 33, 34) else "h264"
                    try:
                        codec_ctx = av.CodecContext.create(codec_name, "r")
                        # No extra options — export_mvs wastes CPU for unused data
                    except Exception as e:
                        log.error("HikvisionSDK: codec init failed: %s", e)
                        break

            if codec_ctx is None:
                continue

            try:
                frames = codec_ctx.decode(av.Packet(chunk))
                for av_frame in frames:
                    bgr = av_frame.to_ndarray(format="bgr24")
                    if self._on_frame and bgr is not None:
                        self._on_frame(bgr, time.time())
            except Exception:
                pass  # skip corrupt/incomplete packets

        if codec_ctx:
            codec_ctx.close()
        # Signal outer loop that this stream is dead so it can reconnect
        self._stream_alive.clear()
        self._running = False

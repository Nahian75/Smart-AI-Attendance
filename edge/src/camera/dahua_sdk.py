"""
Dahua NetSDK capture — native support for Dahua DVR/NVR/IPC proprietary streams.

Supports: Dahua, Amcrest, Lorex, ANNKE, Swann (OEM Dahua), and any device
running Dahua firmware.

Download:
  https://www.dahuasecurity.com/support/downloadCenter
  → "Device Network SDK for Linux 64-bit"
  → Main file: libdhnetsdk.so

Place in: edge/sdk/dahua/libdhnetsdk.so
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

log = logging.getLogger(__name__)

_SDK_DIRS = [
    "/app/sdk/dahua",
    "/opt/dahua/lib",
    "/usr/local/lib/dahua",
]
_SDK_LIB = "libdhnetsdk.so"

EM_REAL_DATA_TYPE_STREAM_HEAD = 0
EM_REAL_DATA_TYPE_STREAM_DATA = 1

LLONG  = ctypes.c_longlong
DWORD  = ctypes.c_uint32
BYTE   = ctypes.c_ubyte
HANDLE = ctypes.c_void_p


class NET_IN_LOGIN_WITH_HIGHLEVEL_SECURITY(ctypes.Structure):
    _fields_ = [
        ("dwSize",      DWORD),
        ("szIP",        ctypes.c_char * 64),
        ("nPort",       ctypes.c_int),
        ("szUserName",  ctypes.c_char * 64),
        ("szPassword",  ctypes.c_char * 64),
        ("emSpecCap",   ctypes.c_int),
        ("pCapParam",   ctypes.c_void_p),
    ]


class NET_OUT_LOGIN_WITH_HIGHLEVEL_SECURITY(ctypes.Structure):
    _fields_ = [
        ("dwSize",      DWORD),
        ("stuDeviceInfo", ctypes.c_char * 384),
        ("nError",      ctypes.c_int),
    ]


REAL_DATA_CALLBACK = ctypes.CFUNCTYPE(
    None,
    LLONG,              # lRealHandle
    DWORD,              # dwDataType
    ctypes.POINTER(BYTE), # pBuffer
    DWORD,              # dwBufSize
    LLONG,              # dwUser
)


def _find_sdk_lib() -> str | None:
    for d in _SDK_DIRS:
        path = os.path.join(d, _SDK_LIB)
        if os.path.exists(path):
            return path
    return ctypes.util.find_library("dhnetsdk")


class DahuaSDKCapture:
    """
    Frame capture using Dahua NetSDK.
    Handles all Dahua proprietary codecs and encryption.
    """

    def __init__(self, host: str, port: int, username: str, password: str,
                 channel: int = 1, stream_type: int = 0):
        self.host        = host
        self.port        = port
        self.username    = username
        self.password    = password
        self.channel     = channel - 1   # Dahua uses 0-based channel index
        self.stream_type = stream_type

        self._sdk:         ctypes.CDLL | None = None
        self._login_id:    int  = 0
        self._real_handle: LLONG = LLONG(0)
        self._running:     bool = False
        self._on_frame:    Callable | None = None
        self._chunk_q:     queue.Queue[bytes] = queue.Queue(maxsize=4)
        self._cb_ref:      REAL_DATA_CALLBACK | None = None
        self._thread:      threading.Thread | None = None

        self._sdk = self._load_sdk()

    @classmethod
    def is_available(cls) -> bool:
        return _find_sdk_lib() is not None

    def start(self, on_frame: Callable) -> bool:
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
            name=f"dhnetsdk-{self.host}-ch{self.channel}",
        )
        self._thread.start()
        log.info("[DahuaSDK] streaming %s:%d ch%d", self.host, self.port, self.channel + 1)
        return True

    def stop(self) -> None:
        self._running = False
        if self._real_handle:
            try:
                self._sdk.CLIENT_StopRealPlay(self._real_handle)
            except Exception:
                pass
        self._logout()

    def _load_sdk(self) -> ctypes.CDLL | None:
        lib_path = _find_sdk_lib()
        if not lib_path:
            log.debug("DahuaSDK: library not found")
            return None
        try:
            sdk = ctypes.CDLL(lib_path, mode=ctypes.RTLD_GLOBAL)
            sdk.CLIENT_Init(None, 0)
            log.info("DahuaSDK loaded: %s", lib_path)
            return sdk
        except Exception as e:
            log.warning("DahuaSDK load failed: %s", e)
            return None

    def _login(self) -> bool:
        in_param              = NET_IN_LOGIN_WITH_HIGHLEVEL_SECURITY()
        in_param.dwSize       = ctypes.sizeof(in_param)
        in_param.szIP         = self.host.encode()
        in_param.nPort        = self.port
        in_param.szUserName   = self.username.encode()
        in_param.szPassword   = self.password.encode()
        in_param.emSpecCap    = 0  # TCP login

        out_param             = NET_OUT_LOGIN_WITH_HIGHLEVEL_SECURITY()
        out_param.dwSize      = ctypes.sizeof(out_param)

        self._sdk.CLIENT_LoginWithHighLevelSecurity.restype = LLONG
        uid = self._sdk.CLIENT_LoginWithHighLevelSecurity(
            ctypes.byref(in_param), ctypes.byref(out_param)
        )
        if not uid:
            err = self._sdk.CLIENT_GetLastError()
            log.warning("DahuaSDK login failed: err=0x%08X host=%s", err, self.host)
            return False
        self._login_id = uid
        log.info("DahuaSDK logged in host=%s", self.host)
        return True

    def _start_preview(self) -> bool:
        def _cb(handle, data_type, buf, buf_size, user):
            if not self._running:
                return
            raw = bytes(buf[:buf_size])
            # Drop the OLDEST chunk when full to maintain low latency.
            if self._chunk_q.full():
                try:
                    self._chunk_q.get_nowait()
                except queue.Empty:
                    pass
            try:
                self._chunk_q.put_nowait(raw)
            except queue.Full:
                pass

        self._cb_ref = REAL_DATA_CALLBACK(_cb)

        self._sdk.CLIENT_RealPlayEx.restype = LLONG
        handle = self._sdk.CLIENT_RealPlayEx(
            self._login_id,
            self.channel,
            None,           # hWnd (no display window)
            self.stream_type,
        )
        if not handle:
            log.warning("DahuaSDK preview failed")
            return False

        self._real_handle = handle
        # CLIENT_SetRealDataCallBackEx2 matches our 5-param CFUNCTYPE (LLONG user).
        # The older Ex variant uses LONG (32-bit) for user, causing stack corruption
        # on 64-bit Linux when the callback fires.
        self._sdk.CLIENT_SetRealDataCallBackEx2(handle, self._cb_ref, 0, 0)
        return True

    def _logout(self) -> None:
        if self._login_id:
            try:
                self._sdk.CLIENT_Logout(self._login_id)
            except Exception:
                pass
            self._login_id = 0

    def _decode_loop(self) -> None:
        try:
            import av
        except ImportError:
            log.error("DahuaSDK: 'av' (PyAV) package required. pip install av")
            self._running = False
            return

        codec_ctx  = None
        codec_name = "h264"

        while self._running:
            try:
                chunk = self._chunk_q.get(timeout=1.0)
            except queue.Empty:
                continue

            if codec_ctx is None:
                if len(chunk) >= 5:
                    b = chunk[4] if len(chunk) > 4 else 0
                    nal_type = (b >> 1) & 0x3F
                    codec_name = "hevc" if nal_type in (32, 33, 34) else "h264"
                try:
                    codec_ctx = av.CodecContext.create(codec_name, "r")
                except Exception as e:
                    log.error("DahuaSDK codec init: %s", e)
                    break

            try:
                for frame in codec_ctx.decode(av.Packet(chunk)):
                    bgr = frame.to_ndarray(format="bgr24")
                    if self._on_frame and bgr is not None:
                        self._on_frame(bgr, time.time())
            except Exception:
                pass

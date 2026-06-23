"""Thread-based RTSP/ONVIF/file reader with auto-reconnect and frame skipping."""
import threading
import time
import cv2
from typing import Callable
from ..utils.logger import get_logger

log = get_logger("rtsp")


class RTSPReader:
    def __init__(self, camera_id: str, rtsp_url: str, fps_target: int = 10,
                 reconnect_delay: int = 5, use_gstreamer: bool = False):
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
        """Return int for webcam index or string for RTSP/file URL."""
        url = self.rtsp_url.strip()
        if url.lstrip("-").isdigit():
            return int(url)
        return url

    def _connect(self) -> bool:
        try:
            if self.use_gstreamer:
                self._cap = cv2.VideoCapture(self._gst_pipeline(), cv2.CAP_GSTREAMER)
            if not self.use_gstreamer or not self._cap.isOpened():
                self._cap = cv2.VideoCapture(self._source())
                self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if self._cap.isOpened():
                log.info(f"[{self.camera_id}] connected to {self.rtsp_url}")
                return True
        except Exception as e:
            log.error(f"[{self.camera_id}] connect error: {e}")
        return False

    def start(self, on_frame: Callable):
        self._running = True
        self._thread = threading.Thread(target=self._loop, args=(on_frame,), daemon=True)
        self._thread.start()

    def _loop(self, on_frame: Callable):
        url = self.rtsp_url.strip()
        is_file = not (url.startswith("rtsp://") or url.startswith("http://") or url.startswith("https://") or url.lstrip("-").isdigit())
        
        src_fps = 30
        skip = max(1, src_fps // max(1, self.fps_target))
        if is_file:
            skip = 1
            
        n = 0
        while self._running:
            if self._cap is None or not self._cap.isOpened():
                if not self._connect():
                    time.sleep(self.reconnect_delay)
                    continue
            ok, frame = self._cap.read()
            if not ok:
                log.warning(f"[{self.camera_id}] read failed, reconnecting")
                if self._cap:
                    self._cap.release()
                self._cap = None
                if is_file:
                    time.sleep(self.reconnect_delay)
                continue
            n += 1
            if n % skip == 0:
                on_frame(frame, time.time())
            if is_file:
                time.sleep(1.0 / self.fps_target)

    def stop(self):
        self._running = False
        if self._cap:
            self._cap.release()

"""YOLOv11 person detector with integrated tracker (Ultralytics)."""
from dataclasses import dataclass
import numpy as np


@dataclass
class Track:
    track_id: int
    bbox: tuple[float, float, float, float]   # x1, y1, x2, y2
    confidence: float

    def is_confirmed(self) -> bool:
        return self.confidence >= 0.4


class YOLODetector:
    """
    Wraps Ultralytics YOLO. Uses model.track() which runs detection +
    ByteTrack/BoT-SORT in one call, giving persistent track IDs for free.
    The device is resolved from gpu.detect() so YOLO automatically uses
    CUDA (NVIDIA/AMD ROCm), Intel XPU, or CPU as available.
    """
    PERSON_CLASS = 0

    def __init__(self, model_path: str = "yolo11s.pt", device: str = "auto",
                 conf: float = 0.45, iou: float = 0.5,
                 tracker_cfg: str = "bytetrack.yaml"):
        from ultralytics import YOLO
        from ..utils.gpu import detect as detect_gpu

        self.conf = conf
        self.iou = iou
        self.tracker_cfg = tracker_cfg

        # Resolve device: explicit arg wins, otherwise auto-detect
        if device == "auto":
            self.device = detect_gpu()["torch_device"]
        else:
            self.device = device

        self.model = YOLO(model_path)

    def track(self, frame: np.ndarray) -> list[Track]:
        results = self.model.track(
            frame, persist=True, classes=[self.PERSON_CLASS],
            conf=self.conf, iou=self.iou, tracker=self.tracker_cfg,
            device=self.device, verbose=False, stream=False,
        )
        out: list[Track] = []
        if not results:
            return out
        r = results[0]
        if r.boxes is None or r.boxes.id is None:
            return out
        for box, tid, c in zip(r.boxes.xyxy.cpu().numpy(),
                               r.boxes.id.cpu().numpy().astype(int),
                               r.boxes.conf.cpu().numpy()):
            out.append(Track(track_id=int(tid), bbox=tuple(box), confidence=float(c)))
        return out

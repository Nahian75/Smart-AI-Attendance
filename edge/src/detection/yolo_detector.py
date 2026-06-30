"""YOLOv11 person detector with integrated tracker (Ultralytics)."""
from dataclasses import dataclass
import numpy as np


@dataclass
class Track:
    track_id: int
    bbox: tuple[float, float, float, float]   # x1, y1, x2, y2
    confidence: float

    def is_confirmed(self) -> bool:
        # 0.35 — matches the YOLO conf floor so no detections are double-filtered
        return self.confidence >= 0.35


@dataclass
class ObjectDetection:
    label: str         # e.g. "backpack", "face mask", "knife"
    bbox: tuple[float, float, float, float]
    confidence: float


# COCO classes to flag as suspicious objects.
# These are detected without tracking (single-frame inference) so they fire
# an alert even for objects that aren't associated with a confirmed person.
SUSPICIOUS_OBJECT_CLASSES: dict[int, str] = {
    24: "backpack",
    26: "handbag",
    28: "suitcase",
    # Uncomment to also flag weapons (classes exist in COCO but rarely detected):
    # 43: "knife",
    # 76: "scissors",
}


class YOLODetector:
    """
    Wraps Ultralytics YOLO. Uses model.track() for person detection +
    ByteTrack tracking. Separately provides detect_objects() for non-person
    classes (bags, suspicious items) without tracking overhead.
    """
    PERSON_CLASS = 0

    def __init__(self, model_path: str = "yolo11s.pt", device: str = "auto",
                 conf: float = 0.35, iou: float = 0.5,
                 tracker_cfg: str = "bytetrack.yaml"):
        from ultralytics import YOLO
        from ..utils.gpu import detect as detect_gpu

        self.conf = conf
        self.iou = iou
        self.tracker_cfg = tracker_cfg

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

    def detect_objects(self, frame: np.ndarray,
                       classes: dict[int, str] | None = None) -> list[ObjectDetection]:
        """Detect suspicious objects (bags, etc.) without tracking.

        Runs a standard detection pass (no ByteTrack) on the given classes.
        Called once per frame by FrameProcessor when detect_bags=True.
        """
        target = classes or SUSPICIOUS_OBJECT_CLASSES
        if not target:
            return []
        results = self.model(
            frame, classes=list(target.keys()),
            conf=0.25, iou=self.iou,
            device=self.device, verbose=False, stream=False,
        )
        out: list[ObjectDetection] = []
        if not results:
            return out
        r = results[0]
        if r.boxes is None:
            return out
        for box, cls_id, conf in zip(r.boxes.xyxy.cpu().numpy(),
                                     r.boxes.cls.cpu().numpy().astype(int),
                                     r.boxes.conf.cpu().numpy()):
            label = target.get(int(cls_id), f"object_{cls_id}")
            out.append(ObjectDetection(label=label, bbox=tuple(box), confidence=float(conf)))
        return out

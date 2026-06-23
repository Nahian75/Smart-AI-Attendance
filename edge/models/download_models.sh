#!/usr/bin/env bash
set -e
mkdir -p weights
echo "Downloading YOLOv11 weights..."
python -c "from ultralytics import YOLO; YOLO('yolo11s.pt')"
echo "InsightFace buffalo_l downloads automatically on first run."
echo "Place your anti-spoof ONNX model at edge/models/weights/antispoof.onnx"

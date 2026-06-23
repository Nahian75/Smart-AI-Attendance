"""
Runtime GPU detection — picks the best available accelerator and returns
settings consumed by YOLO, InsightFace, and ONNX Runtime.

Priority order: NVIDIA CUDA > AMD ROCm > Intel OpenVINO/XPU > DirectML > CPU.
Each path falls back gracefully: if the provider initialises but then fails
during inference, ONNX Runtime automatically falls to the next provider in
the list.
"""
import logging
import os

log = logging.getLogger(__name__)

_CACHED: dict | None = None


def detect() -> dict:
    """
    Return a dict:
        device_type   – "nvidia" | "amd" | "intel" | "directml" | "cpu"
        ort_providers – list[str] passed to onnxruntime.InferenceSession
        torch_device  – str passed to YOLO / PyTorch  ("cuda" | "xpu" | "cpu")
        insightface_ctx – int  0 = GPU  |  -1 = CPU
        label         – human-readable description for the startup log
    """
    global _CACHED
    if _CACHED is not None:
        return _CACHED

    # Allow explicit override via env var (useful in containers)
    override = os.getenv("DEVICE", "").lower()
    if override == "cuda":
        _CACHED = _make("nvidia", ["CUDAExecutionProvider", "CPUExecutionProvider"],
                        "cuda", 0, "NVIDIA CUDA (forced via DEVICE=cuda)")
        return _CACHED
    if override == "rocm":
        _CACHED = _make("amd", ["ROCMExecutionProvider", "CPUExecutionProvider"],
                        "cuda", 0, "AMD ROCm (forced via DEVICE=rocm)")
        return _CACHED
    if override == "openvino":
        _CACHED = _make("intel", ["OpenVINOExecutionProvider", "CPUExecutionProvider"],
                        "cpu", -1, "Intel OpenVINO (forced via DEVICE=openvino)")
        return _CACHED
    if override == "cpu":
        _CACHED = _make("cpu", ["CPUExecutionProvider"],
                        "cpu", -1, "CPU (forced via DEVICE=cpu)")
        return _CACHED

    # Auto-detect from available ONNX Runtime providers
    try:
        import onnxruntime as ort
        available = set(ort.get_available_providers())
        log.debug("ONNX Runtime providers available: %s", available)

        if "CUDAExecutionProvider" in available:
            _CACHED = _make("nvidia",
                            ["CUDAExecutionProvider", "CPUExecutionProvider"],
                            "cuda", 0, "NVIDIA CUDA")
            return _CACHED

        if "ROCMExecutionProvider" in available:
            _CACHED = _make("amd",
                            ["ROCMExecutionProvider", "CPUExecutionProvider"],
                            "cuda", 0,
                            "AMD ROCm (CUDA compat mode for PyTorch/Ultralytics)")
            return _CACHED

        if "OpenVINOExecutionProvider" in available:
            _CACHED = _make("intel",
                            ["OpenVINOExecutionProvider", "CPUExecutionProvider"],
                            _xpu_device(), -1, "Intel OpenVINO")
            return _CACHED

        if "DmlExecutionProvider" in available:
            _CACHED = _make("directml",
                            ["DmlExecutionProvider", "CPUExecutionProvider"],
                            "cpu", -1,
                            "DirectML (AMD/Intel/NVIDIA on Windows)")
            return _CACHED

    except ImportError:
        log.warning("onnxruntime not importable — falling back to CPU.")

    # Intel XPU via Intel Extension for PyTorch (IPEX)
    try:
        import torch
        if hasattr(torch, "xpu") and torch.xpu.is_available():
            _CACHED = _make("intel",
                            ["CPUExecutionProvider"],
                            "xpu", -1,
                            "Intel XPU via IPEX (ORT inference on CPU)")
            return _CACHED
    except (ImportError, Exception):
        pass

    _CACHED = _make("cpu", ["CPUExecutionProvider"], "cpu", -1, "CPU")
    return _CACHED


def _make(device_type, ort_providers, torch_device, insightface_ctx, label):
    return {
        "device_type": device_type,
        "ort_providers": ort_providers,
        "torch_device": torch_device,
        "insightface_ctx": insightface_ctx,
        "label": label,
    }


def _xpu_device() -> str:
    """Return 'xpu' if Intel Extension for PyTorch is available, else 'cpu'."""
    try:
        import torch
        return "xpu" if hasattr(torch, "xpu") and torch.xpu.is_available() else "cpu"
    except (ImportError, Exception):
        return "cpu"


def log_info() -> None:
    """Log the detected GPU configuration at startup."""
    cfg = detect()
    log.info(
        "GPU: %s | ORT providers: %s | Torch device: %s",
        cfg["label"],
        ", ".join(cfg["ort_providers"]),
        cfg["torch_device"],
    )

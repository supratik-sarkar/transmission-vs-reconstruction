"""Device routing.

Supports Apple Silicon (MPS), CUDA and CPU without hard-coding any machine
path. Torch is OPTIONAL: the coordinating code -- corpus, atomizer, sampling,
matcher, editor, estimators, bootstrap, export -- runs entirely without it.

CUDA dependencies are never installed on macOS.
"""

from __future__ import annotations

import platform
import shutil
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DeviceReport:
    platform: str
    machine: str
    torch_available: bool
    cuda_available: bool
    mps_available: bool
    selected: str
    notes: tuple[str, ...] = ()


def _torch():
    try:
        import torch  # noqa: PLC0415

        return torch
    except Exception:
        return None


def detect(prefer: str = "auto") -> DeviceReport:
    torch = _torch()
    notes: list[str] = []
    cuda = mps = False
    if torch is not None:
        try:
            cuda = bool(torch.cuda.is_available())
        except Exception:
            notes.append("torch.cuda probe failed")
        try:
            mps = bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())
        except Exception:
            notes.append("torch.mps probe failed")
    else:
        notes.append("torch not installed: CPU-only coordination, which is supported")

    if prefer != "auto":
        selected = prefer
    elif cuda:
        selected = "cuda"
    elif mps:
        selected = "mps"
    else:
        selected = "cpu"

    if platform.system() == "Darwin" and selected == "cuda":
        raise RuntimeError("CUDA was requested on macOS; use mps or cpu instead")

    return DeviceReport(
        platform=platform.system(),
        machine=platform.machine(),
        torch_available=torch is not None,
        cuda_available=cuda,
        mps_available=mps,
        selected=selected,
        notes=tuple(notes),
    )


def diagnostics() -> dict[str, object]:
    report = detect()
    return {
        "platform": report.platform,
        "machine": report.machine,
        "python": platform.python_version(),
        "torch_available": report.torch_available,
        "cuda_available": report.cuda_available,
        "mps_available": report.mps_available,
        "selected_device": report.selected,
        "nvidia_smi": bool(shutil.which("nvidia-smi")),
        "notes": list(report.notes),
    }

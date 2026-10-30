"""Hardware detection for llama.cpp acceleration defaults.

Used to turn on Flash Attention and multi-token prediction only where they can
actually help: a GPU must be present, and MTP additionally needs a draft model.
Everything here is best-effort — a missing probe tool just means "no GPU".
"""
from __future__ import annotations

import shutil
import subprocess


def _run(cmd: list[str], timeout: float = 4.0) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except Exception:
        return None


def detect_gpu() -> dict[str, object]:
    """Return ``{"vendor", "name", "count"}``; vendor is ``none`` when unknown."""
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        result = _run([nvidia_smi, "--query-gpu=name", "--format=csv,noheader"])
        if result is not None and result.returncode == 0:
            names = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
            if names:
                return {"vendor": "nvidia", "name": names[0], "count": len(names)}

    if shutil.which("rocminfo") or shutil.which("rocm-smi"):
        return {"vendor": "amd", "name": "AMD GPU", "count": 1}

    lspci = shutil.which("lspci")
    if lspci:
        result = _run([lspci])
        text = (result.stdout or "").lower() if result is not None else ""
        for marker, vendor, label in (
            ("nvidia", "nvidia", "NVIDIA GPU"),
            ("advanced micro devices", "amd", "AMD GPU"),
            ("intel corporation", "intel", "Intel GPU"),
        ):
            if marker in text:
                return {"vendor": vendor, "name": label, "count": 1}

    return {"vendor": "none", "name": "", "count": 0}


def has_gpu() -> bool:
    return str(detect_gpu().get("vendor", "none")) not in {"", "none"}


def draft_model_configured(payload: dict[str, object]) -> bool:
    """True when a speculative/MTP draft model is available to pair with."""
    if str(payload.get("llama_mtp_draft_model", "")).strip():
        return True
    repo = str(payload.get("llama_hf_draft_repo", "")).strip()
    file_name = str(payload.get("llama_hf_draft_file", "")).strip()
    return bool(repo and file_name)


def acceleration_defaults(payload: dict[str, object]) -> dict[str, bool]:
    """Recommended acceleration flags for this machine and payload."""
    gpu = has_gpu()
    return {"flash_attn": gpu, "mtp": gpu and draft_model_configured(payload)}


__all__ = ["acceleration_defaults", "detect_gpu", "draft_model_configured", "has_gpu"]

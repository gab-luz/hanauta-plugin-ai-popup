"""Camera capture for voice mode.

Grabs a low-resolution frame from a V4L2 device (a webcam path like
``/dev/video0``) or from an HTTP/RTSP stream, throttled to a configurable
interval, so an omni/vision model can "see" while a conversation runs.

Everything here is best-effort: a missing camera or ffmpeg never breaks a
conversation turn, the frame is simply omitted.
"""
from __future__ import annotations

import base64
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from .runtime import AI_STATE_DIR

CAMERA_DEFAULTS: dict[str, object] = {
    "camera_enabled": False,
    "camera_source": "/dev/video0",
    "camera_resolution": "640x480",
    "camera_interval_seconds": "10",
}

CAMERA_DIR = AI_STATE_DIR / "voice-camera"

# Maximum edge, so "low resolution" stays cheap for the vision encoder.
_MAX_WIDTH = 1280
_MAX_HEIGHT = 720
_MIN_EDGE = 64

# Throttle state: last capture time + last frame path.
_FRAME_CACHE: dict[str, object] = {"ts": 0.0, "path": ""}

# Optional observer (the overlay) told when a source starts capturing.
_CAPTURE_LISTENER: Callable[[str], None] | None = None


def set_capture_listener(listener: Callable[[str], None] | None) -> None:
    """Register a callback fired as ``listener(kind)`` when capture starts."""
    global _CAPTURE_LISTENER
    _CAPTURE_LISTENER = listener


def notify_capture(kind: str) -> None:
    """Best-effort notification; a broken listener must never break a capture."""
    listener = _CAPTURE_LISTENER
    if listener is None:
        return
    try:
        listener(kind)
    except Exception:
        pass


def parse_resolution(value: object, fallback: tuple[int, int] = (640, 480)) -> tuple[int, int]:
    """Parse ``"640x480"`` / ``"640X480"`` / ``"640,480"`` into a clamped tuple."""
    raw = str(value or "").strip().lower().replace(",", "x").replace(" ", "")
    if "x" in raw:
        left, _, right = raw.partition("x")
        try:
            width = int(float(left))
            height = int(float(right))
        except (TypeError, ValueError):
            return fallback
    else:
        try:
            width = height = int(float(raw))
        except (TypeError, ValueError):
            return fallback
    width = max(_MIN_EDGE, min(_MAX_WIDTH, width))
    height = max(_MIN_EDGE, min(_MAX_HEIGHT, height))
    if (width, height) == (0, 0):
        return fallback
    return width, height


def parse_interval(value: object, fallback: float = 10.0) -> float:
    try:
        seconds = float(str(value or "").strip())
    except (TypeError, ValueError):
        return fallback
    # Never hammer the device: 1s floor, 1h ceiling.
    return max(1.0, min(3600.0, seconds))


def camera_enabled(config: dict[str, object]) -> bool:
    return bool(config.get("camera_enabled", False)) and bool(
        str(config.get("camera_source", "")).strip()
    )


def _source_is_stream(source: str) -> bool:
    lowered = source.strip().lower()
    return lowered.startswith(("http://", "https://", "rtsp://", "rtmp://"))


def capture_snapshot(config: dict[str, object], dest_dir: Path | None = None) -> Path:
    """Capture a single frame and return its path. Raises RuntimeError on failure."""
    source = str(config.get("camera_source", "")).strip() or str(CAMERA_DEFAULTS["camera_source"])
    width, height = parse_resolution(config.get("camera_resolution", CAMERA_DEFAULTS["camera_resolution"]))
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for camera capture.")

    target_dir = Path(dest_dir) if dest_dir is not None else CAMERA_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    output = target_dir / f"frame_{int(time.time() * 1000)}.jpg"

    command = [ffmpeg, "-y", "-loglevel", "error"]
    if _source_is_stream(source):
        command += ["-rtsp_transport", "tcp", "-i", source]
    else:
        command += ["-f", "video4linux2", "-i", source]
    command += [
        "-frames:v", "1",
        "-vf", f"scale={width}:{height}",
        "-q:v", "4",
        str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
    if result.returncode != 0 or not output.exists() or output.stat().st_size <= 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        reason = detail[-1] if detail else "unknown error"
        raise RuntimeError(f"Camera capture failed for {source}: {reason}")
    return output


def encode_image_data_url(path: Path) -> str:
    data = Path(path).read_bytes()
    return "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")


def camera_frame_data_url(config: dict[str, object], *, force: bool = False) -> list[str]:
    """Return ``[data_url]`` for the current frame, honouring the capture interval.

    Returns an empty list when the camera is disabled or the frame cannot be
    captured, so callers can pass the result straight into a prompt.
    """
    if not camera_enabled(config):
        return []
    interval = parse_interval(config.get("camera_interval_seconds", CAMERA_DEFAULTS["camera_interval_seconds"]))
    now = time.time()
    last_ts = float(_FRAME_CACHE.get("ts", 0.0) or 0.0)
    cached_path = str(_FRAME_CACHE.get("path", "") or "")

    if not force and cached_path and (now - last_ts) < interval and Path(cached_path).exists():
        return [encode_image_data_url(Path(cached_path))]

    try:
        frame = capture_snapshot(config)
    except Exception:
        # Best effort: a broken/unplugged camera must not break a conversation turn.
        return []
    _FRAME_CACHE["ts"] = now
    _FRAME_CACHE["path"] = str(frame)
    notify_capture("camera")
    return [encode_image_data_url(frame)]


__all__ = [
    "CAMERA_DEFAULTS",
    "CAMERA_DIR",
    "camera_enabled",
    "camera_frame_data_url",
    "capture_snapshot",
    "encode_image_data_url",
    "notify_capture",
    "set_capture_listener",
    "parse_interval",
    "parse_resolution",
]

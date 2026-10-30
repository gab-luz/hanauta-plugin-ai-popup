"""Low-resolution screen capture for voice mode.

Grabs a downscaled screenshot so a vision/omni model can "see" what the user is
looking at — a game, a document, a terminal — and talk about it. Like
:mod:`hanauta_aipopup.camera` this is entirely best-effort: a missing display or
capture tool never breaks a conversation turn, the image is simply omitted.

The frame is deliberately small (default 960x540, clamped to 1920x1080). A full
4K grab costs thousands of vision tokens for no extra understanding; a low
resolution frame keeps the whole screen readable while staying cheap.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from .camera import encode_image_data_url, notify_capture, parse_interval
from .runtime import AI_STATE_DIR

SCREEN_DEFAULTS: dict[str, object] = {
    "screen_enabled": False,
    "screen_resolution": "960x540",
    # Auto capture: a new frame is only taken once the previous one is this old.
    # 30s keeps a game readable without spamming the vision encoder.
    "screen_interval_seconds": "30",
    "screen_display": "",
}

SCREEN_DIR = AI_STATE_DIR / "voice-screen"

# Keep screen frames in the same cheap range as camera frames.
_MAX_WIDTH = 1920
_MAX_HEIGHT = 1080
_MIN_EDGE = 64

_FRAME_CACHE: dict[str, object] = {"ts": 0.0, "path": ""}

# Per-turn cache: one vision call per turn may reuse the frame it already has,
# so a tool loop or a retry never re-captures the screen behind the user.
_TURN_CACHE: dict[str, object] = {"turn": "", "path": ""}

# Never let auto capture run faster than this, even if configured lower.
_MIN_INTERVAL_SECONDS = 5.0


def screen_interval(config: dict[str, object]) -> float:
    raw = config.get("screen_interval_seconds", SCREEN_DEFAULTS["screen_interval_seconds"])
    return max(_MIN_INTERVAL_SECONDS, parse_interval(raw, fallback=30.0))


def begin_turn() -> None:
    """Start a new conversation turn (clears the per-turn frame reuse)."""
    _TURN_CACHE["turn"] = ""
    _TURN_CACHE["path"] = ""


def screen_display(config: dict[str, object]) -> str:
    """Return the X display to capture, e.g. ``:0.0`` (empty on Wayland)."""
    explicit = str(config.get("screen_display", "")).strip()
    if explicit:
        return explicit
    display = str(os.environ.get("DISPLAY", "")).strip()
    if display and "." not in display.partition(":")[2]:
        display = f"{display}.0"
    return display


def screen_enabled(config: dict[str, object]) -> bool:
    if not bool(config.get("screen_enabled", False)):
        return False
    # Either an X display or a Wayland session (grim) must be available.
    return bool(screen_display(config)) or bool(os.environ.get("WAYLAND_DISPLAY", "").strip())


def _parse_dimensions(value: object, fallback: tuple[int, int]) -> tuple[int, int]:
    """Parse ``"960x540"`` with the screen's own (larger) clamp.

    ``camera.parse_resolution`` caps at 1280x720 for device frames; a screenshot
    may legitimately be 1920x1080 and still count as "low resolution".
    """
    raw = str(value or "").strip().lower().replace(",", "x").replace(" ", "")
    if "x" in raw:
        left, _, right = raw.partition("x")
        try:
            width, height = int(float(left)), int(float(right))
        except (TypeError, ValueError):
            return fallback
    else:
        try:
            width = height = int(float(raw))
        except (TypeError, ValueError):
            return fallback
    return max(_MIN_EDGE, min(_MAX_WIDTH, width)), max(_MIN_EDGE, min(_MAX_HEIGHT, height))


def screen_resolution(config: dict[str, object]) -> tuple[int, int]:
    return _parse_dimensions(
        config.get("screen_resolution", SCREEN_DEFAULTS["screen_resolution"]),
        fallback=(960, 540),
    )


def _ffmpeg_scale(width: int, height: int) -> str:
    # Force both edges, so the vision encoder sees a stable, small frame.
    return f"scale={width}:{height}:force_original_aspect_ratio=decrease"


def capture_screenshot(config: dict[str, object], dest_dir: Path | None = None) -> Path:
    """Capture a downscaled screenshot and return its path.

    Raises ``RuntimeError`` when no capture path works, so the UI can show the
    reason instead of silently sending nothing.
    """
    width, height = screen_resolution(config)
    target_dir = Path(dest_dir) if dest_dir is not None else SCREEN_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    output = target_dir / f"screen_{int(time.time() * 1000)}.jpg"
    errors: list[str] = []

    ffmpeg = shutil.which("ffmpeg")
    display = screen_display(config)
    if ffmpeg and display:
        command = [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-f",
            "x11grab",
            "-i",
            display,
            "-frames:v",
            "1",
            "-vf",
            _ffmpeg_scale(width, height),
            "-q:v",
            "5",
            str(output),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
        if result.returncode == 0 and output.exists() and output.stat().st_size > 0:
            return output
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        errors.append(detail[-1] if detail else f"ffmpeg x11grab failed for {display}")

    # Wayland: grim captures the compositor, then we downscale with ffmpeg.
    grim = shutil.which("grim")
    if grim and os.environ.get("WAYLAND_DISPLAY", "").strip():
        raw = target_dir / f"screen_{int(time.time() * 1000)}.png"
        result = subprocess.run([grim, str(raw)], capture_output=True, text=True, timeout=20, check=False)
        if result.returncode == 0 and raw.exists() and raw.stat().st_size > 0:
            if ffmpeg:
                scaled = subprocess.run(
                    [ffmpeg, "-y", "-loglevel", "error", "-i", str(raw), "-vf", _ffmpeg_scale(width, height),
                     "-q:v", "5", str(output)],
                    capture_output=True, text=True, timeout=20, check=False,
                )
                if scaled.returncode == 0 and output.exists() and output.stat().st_size > 0:
                    raw.unlink(missing_ok=True)
                    return output
            # No downscaler available: the raw PNG still works, it just costs more tokens.
            return raw
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        errors.append(detail[-1] if detail else "grim failed")

    if not ffmpeg and not grim:
        errors.append("ffmpeg (X11) or grim (Wayland) is required for screenshots")
    raise RuntimeError("Screen capture failed: " + ("; ".join(errors) or "no display detected"))


def screen_frame_data_url(config: dict[str, object], *, force: bool = False, turn_id: str = "") -> list[str]:
    """Return ``[data_url]`` for the current screenshot, honouring the interval.

    ``turn_id`` makes repeated calls inside one turn reuse a single frame, so a
    follow-up question about the same moment never forces a fresh capture.
    Returns an empty list when screen sharing is off or capture fails.
    """
    if not screen_enabled(config):
        return []
    turn = str(turn_id or "").strip()
    if turn and _TURN_CACHE.get("turn") == turn:
        cached_turn_path = str(_TURN_CACHE.get("path", "") or "")
        if cached_turn_path and Path(cached_turn_path).exists():
            return [encode_image_data_url(Path(cached_turn_path))]

    interval = screen_interval(config)
    now = time.time()
    last_ts = float(_FRAME_CACHE.get("ts", 0.0) or 0.0)
    cached_path = str(_FRAME_CACHE.get("path", "") or "")

    if not force and cached_path and (now - last_ts) < interval and Path(cached_path).exists():
        if turn:
            _TURN_CACHE["turn"] = turn
            _TURN_CACHE["path"] = cached_path
        return [encode_image_data_url(Path(cached_path))]

    try:
        frame = capture_screenshot(config)
    except Exception:
        # Never break a turn because the screen could not be grabbed.
        return []
    _FRAME_CACHE["ts"] = now
    _FRAME_CACHE["path"] = str(frame)
    if turn:
        _TURN_CACHE["turn"] = turn
        _TURN_CACHE["path"] = str(frame)
    notify_capture("screen")
    return [encode_image_data_url(frame)]


__all__ = [
    "SCREEN_DEFAULTS",
    "SCREEN_DIR",
    "begin_turn",
    "capture_screenshot",
    "screen_display",
    "screen_enabled",
    "screen_frame_data_url",
    "screen_interval",
    "screen_resolution",
]

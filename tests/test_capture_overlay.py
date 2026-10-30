import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from hanauta_aipopup.camera import notify_capture, set_capture_listener  # noqa: E402
from hanauta_aipopup.overlay import CaptureOverlay, CAPTURE_SOUNDS, capture_sound_path  # noqa: E402

_APP = QApplication.instance() or QApplication([])


def test_chimes_are_generated_per_source():
    for kind in CAPTURE_SOUNDS:
        path = capture_sound_path(kind)
        assert path.exists()
        assert path.stat().st_size > 44
        assert path.read_bytes()[:4] == b"RIFF"
    # Different sources must be distinguishable by ear.
    assert CAPTURE_SOUNDS["camera"] != CAPTURE_SOUNDS["screen"]


def test_overlay_tracks_enabled_sources():
    overlay = CaptureOverlay()
    overlay.set_active(["screen"])
    assert overlay.active_sources() == ["screen"]
    # Order is normalised, so repeated syncs do not thrash the widget.
    overlay.set_active(["camera", "screen"])
    assert overlay.active_sources() == ["camera", "screen"]
    overlay.set_active([])
    assert overlay.active_sources() == []


def test_capture_trigger_marks_the_source_active():
    overlay = CaptureOverlay()
    seen: list[str] = []
    set_capture_listener(lambda kind: (seen.append(kind), overlay.trigger.emit(kind)))
    try:
        notify_capture("camera")
    finally:
        set_capture_listener(None)
    assert seen == ["camera"]
    assert "camera" in overlay.active_sources()
    assert overlay._caption == "Camera capture started"


def test_listener_errors_never_escape():
    def boom(kind: str) -> None:
        raise RuntimeError(kind)

    set_capture_listener(boom)
    try:
        notify_capture("screen")  # must not raise
    finally:
        set_capture_listener(None)

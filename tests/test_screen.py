import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from hanauta_aipopup import screen  # noqa: E402


def test_disabled_screen_sends_nothing():
    assert screen.screen_enabled({"screen_enabled": False}) is False
    assert screen.screen_frame_data_url({"screen_enabled": False}) == []


def test_resolution_is_clamped_to_cheap_frames():
    assert screen.screen_resolution({"screen_resolution": "960x540"}) == (960, 540)
    assert screen.screen_resolution({"screen_resolution": "3840x2160"}) == (1920, 1080)
    assert screen.screen_resolution({"screen_resolution": "10x10"}) == (64, 64)
    assert screen.screen_resolution({"screen_resolution": "garbage"}) == (960, 540)


def test_display_defaults_to_environment_and_gets_a_screen_number(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    assert screen.screen_display({}) == ":0.0"
    assert screen.screen_display({"screen_display": ":1.0"}) == ":1.0"


def test_bad_display_raises_a_readable_error(monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    if not os.environ.get("DISPLAY"):
        pytest.skip("no X display available to attempt a capture")
    with pytest.raises(RuntimeError) as excinfo:
        screen.capture_screenshot({"screen_resolution": "320x180", "screen_display": ":99.9"})
    assert "Screen capture failed" in str(excinfo.value)


def test_failing_capture_never_breaks_a_turn(monkeypatch):
    # Enabled + broken display: the frame is simply omitted.
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    config = {"screen_enabled": True, "screen_resolution": "320x180", "screen_display": ":99.9"}
    assert screen.screen_frame_data_url(config, force=True) == []

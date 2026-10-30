import os
import pathlib
import sys
import tempfile

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


def test_focused_window_geometry_is_parsed(monkeypatch):
    class Result:
        returncode = 0
        stdout = "WINDOW=123\nX=40\nY=60\nWIDTH=1000\nHEIGHT=700\nSCREEN=0\n"

    monkeypatch.setattr(screen.shutil, "which", lambda name: "/usr/bin/xdotool")
    monkeypatch.setattr(screen.subprocess, "run", lambda *a, **k: Result())
    assert screen.focused_window_region(":0") == (40, 60, 1000, 700)


def test_focused_window_geometry_falls_back(monkeypatch):
    monkeypatch.setattr(screen.shutil, "which", lambda name: None)
    assert screen.focused_window_region(":0") is None

    class Failed:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(screen.shutil, "which", lambda name: "/usr/bin/xdotool")
    monkeypatch.setattr(screen.subprocess, "run", lambda *a, **k: Failed())
    assert screen.focused_window_region(":0") is None


def test_filter_upscales_small_windows_only():
    small = (0, 0, 400, 300)
    large = (0, 0, 2560, 1440)
    assert screen._capture_filter(960, 540, small, True) == "scale=960:-2:flags=lanczos"
    # Big sources and upscale=off keep the aspect-preserving downscale.
    assert "force_original_aspect_ratio=decrease" in screen._capture_filter(960, 540, large, True)
    assert "force_original_aspect_ratio=decrease" in screen._capture_filter(960, 540, small, False)
    assert "force_original_aspect_ratio=decrease" in screen._capture_filter(960, 540, None, True)


def test_auto_capture_interval_has_a_sane_floor():
    # A too-short interval is clamped, and the default is a relaxed 30s.
    assert screen.screen_interval({"screen_interval_seconds": "1"}) == 5.0
    assert screen.screen_interval({"screen_interval_seconds": "30"}) == 30.0
    assert screen.screen_interval({}) == 30.0


def test_same_turn_reuses_one_frame(monkeypatch):
    calls = {"n": 0}

    def fake_capture(config, dest_dir=None):
        calls["n"] += 1
        path = pathlib.Path(tempfile.mkdtemp()) / f"frame_{calls['n']}.jpg"
        path.write_bytes(b"\xff\xd8\xff\xd9")
        return path

    monkeypatch.setattr(screen, "capture_screenshot", fake_capture)
    config = {"screen_enabled": True, "screen_interval_seconds": "30"}
    first = screen.screen_frame_data_url(config, force=True, turn_id="t1")
    second = screen.screen_frame_data_url(config, force=True, turn_id="t1")
    assert first and first == second
    assert calls["n"] == 1  # a repeat call inside a turn never re-captures

    screen.begin_turn()
    third = screen.screen_frame_data_url(config, force=True, turn_id="t2")
    assert third and calls["n"] == 2


def test_failing_capture_never_breaks_a_turn(monkeypatch):
    # Enabled + broken display: the frame is simply omitted.
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    config = {"screen_enabled": True, "screen_resolution": "320x180", "screen_display": ":99.9"}
    assert screen.screen_frame_data_url(config, force=True) == []

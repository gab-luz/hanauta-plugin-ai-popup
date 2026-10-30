"""Tests for camera capture settings and degradation."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hanauta_aipopup import camera, tts  # noqa: E402


@pytest.mark.parametrize(
    "value,expected",
    [
        ("640x480", (640, 480)),
        ("320X240", (320, 240)),
        ("800,600", (800, 600)),
        ("4000x4000", (1280, 720)),
        ("8x8", (64, 64)),
        ("nonsense", (640, 480)),
        ("", (640, 480)),
        (None, (640, 480)),
    ],
)
def test_parse_resolution(value, expected):
    assert camera.parse_resolution(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [("10", 10.0), ("0", 1.0), ("-5", 1.0), ("99999", 3600.0), ("abc", 10.0)],
)
def test_parse_interval(value, expected):
    assert camera.parse_interval(value) == expected


def test_disabled_camera_returns_no_images():
    assert camera.camera_frame_data_url({"camera_enabled": False}) == []


def test_enabled_camera_without_source_returns_no_images():
    assert camera.camera_frame_data_url({"camera_enabled": True, "camera_source": ""}) == []


def test_missing_device_degrades_to_no_images():
    config = {"camera_enabled": True, "camera_source": "/dev/definitely-not-a-camera"}
    assert camera.camera_frame_data_url(config) == []


def test_prompt_helper_never_raises_for_broken_camera():
    assert tts._camera_message_images(
        {"camera_enabled": True, "camera_source": "/dev/definitely-not-a-camera"}
    ) == []


def test_encode_image_data_url(tmp_path):
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"fakejpegbytes")
    url = camera.encode_image_data_url(frame)
    assert url.startswith("data:image/jpeg;base64,")
    assert url.split(",", 1)[1] == "ZmFrZWpwZWdieXRlcw=="


def test_capture_snapshot_raises_for_missing_source():
    with pytest.raises(RuntimeError):
        camera.capture_snapshot({"camera_source": "/dev/definitely-not-a-camera"})

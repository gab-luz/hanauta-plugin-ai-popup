import logging
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from hanauta_aipopup.app import _BenignNoiseFilter  # noqa: E402


def _record(message: str, level: int = logging.WARNING) -> logging.LogRecord:
    return logging.LogRecord("hanauta.ai_popup", level, __file__, 1, message, None, None)


def test_qt_startup_chatter_is_dropped():
    noise = _BenignNoiseFilter()
    for message in (
        "Qt[qt.multimedia.ffmpeg] :0 Using Qt multimedia with FFmpeg version 9.0.1 LGPL version 2.1 or later",
        "Qt[qt.core.qfuture.continuations] :0 Parent future has 2 result(s), but only the first result will be handled in the continuation.",
        "Qt[default] :0 GPUInfo not initialized on GpuInfoUpdate",
        "Qt[qt.svg.draw] :0 The requested buffer size is too big, ignoring",
    ):
        assert noise.filter(_record(message)) is False, message


def test_actionable_messages_survive():
    noise = _BenignNoiseFilter()
    assert noise.filter(_record("LFM3 autostart: ok=False runway")) is True
    assert noise.filter(_record("Port 8082 is already in use by another service")) is True
    # Even a filtered pattern must pass when it is a real error.
    assert noise.filter(_record("Qt[qt.multimedia.ffmpeg] decoder crashed", logging.ERROR)) is True

import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6.QtWidgets")

from hanauta_aipopup.ui_panel import SidebarPanel  # noqa: E402


class _PanelStub:
    """Captures what the real handler sets without building the whole panel."""

    def __init__(self) -> None:
        self._voice_last_transcript = ""
        self._voice_last_emotion = "neutral"
        self._voice_last_status = ""
        self.view_calls: list[tuple[bool, bool]] = []

    def _update_voice_mode_view(self, listening: bool = False, speaking: bool = False) -> None:
        self.view_calls.append((listening, speaking))


def test_partial_transcript_reaches_the_voice_view_while_speaking():
    # Live transcription is only useful if each partial updates the state the
    # web view renders, not just the final transcript.
    panel = _PanelStub()
    SidebarPanel._handle_voice_transcript_partial(panel, "  hello wor  ")
    assert panel._voice_last_transcript == "hello wor"
    assert panel._voice_last_status == "Listening"
    assert panel.view_calls == [(True, False)]

    SidebarPanel._handle_voice_transcript_partial(panel, "hello world")
    assert panel._voice_last_transcript == "hello world"
    assert panel.view_calls == [(True, False), (True, False)]


def test_blank_partial_does_not_clobber_the_transcript():
    panel = _PanelStub()
    SidebarPanel._handle_voice_transcript_partial(panel, "   ")
    assert panel._voice_last_transcript == ""
    assert panel.view_calls == []

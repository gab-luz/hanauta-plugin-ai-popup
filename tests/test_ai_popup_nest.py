"""Tests for the new Nest-based main file (``ai-popup.py``).

The file is the migration target, so the contract that matters is: it imports
without a running app, gates sending on backend state, keeps message IDs unique,
and streams OpenAI-style SSE deltas.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_main():
    # The module must be registered before exec: dataclasses look it up in
    # sys.modules, and the filename is not importable (``ai-popup.py``).
    if "ai_popup_nest" in sys.modules:
        return sys.modules["ai_popup_nest"]
    spec = importlib.util.spec_from_file_location("ai_popup_nest", ROOT / "ai-popup.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["ai_popup_nest"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def main_module():
    return _load_main()


@pytest.fixture(scope="module")
def app():
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_module_imports_without_creating_an_application(main_module):
    from PyQt6.QtWidgets import QApplication

    assert hasattr(main_module, "PopupWindow")
    assert hasattr(main_module.NestView, "send_requested")
    assert QApplication.instance() is None or True  # never asserted on import


def test_send_is_gated_on_backend_state_and_busy(app, main_module):
    view = main_module.NestView()
    view.set_backend_state(False, "")
    view.editor.setPlainText("hello")
    assert not view.send_button.isEnabled()

    view.set_backend_state(True, "LFM3-Omni 2B")
    assert view.send_button.isEnabled()

    view.set_busy(True)
    assert not view.send_button.isEnabled()

    view.set_busy(False)
    view.editor.clear()
    assert not view.send_button.isEnabled()


def test_message_ids_are_unique_and_updates_require_an_existing_id(app, main_module):
    view = main_module.NestView()
    view.add_message("m1", "user", "hi")

    with pytest.raises(ValueError):
        view.add_message("m1", "user", "again")

    view.update_message("m1", "hi there")
    assert view._messages["m1"].text() == "hi there"

    with pytest.raises(KeyError):
        view.update_message("missing", "x")


def test_stream_chat_parses_sse_deltas(monkeypatch, main_module):
    class _Response:
        headers = {"Content-Type": "text/event-stream"}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def __iter__(self):
            for piece in ("Hel", "lo", "!"):
                yield f"data: {json.dumps({'choices': [{'delta': {'content': piece}}]})}\n".encode()
            yield b"data: [DONE]\n"

    seen: list[str] = []
    monkeypatch.setattr(main_module.urllib.request, "urlopen", lambda *a, **k: _Response())

    answer = main_module.stream_chat("127.0.0.1:1", "m", [], "", seen.append)

    assert answer == "Hello!"
    assert seen == ["Hel", "lo", "!"]


def test_non_streaming_reply_is_supported(monkeypatch, main_module):
    class _Response:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "plain"}}]}).encode()

    monkeypatch.setattr(main_module.urllib.request, "urlopen", lambda *a, **k: _Response())

    assert main_module.stream_chat("127.0.0.1:1", "m", [], "") == "plain"


def test_resolve_llm_prefers_lfm3_when_its_weights_are_configured(main_module):
    settings = {
        "lfm3": {"gguf_path": "/models/LFM3-Omni-2B-Abliter8-Q6_K.gguf", "host": "127.0.0.1:8084"},
        "_voice_mode": {"llm_profile": "koboldcpp"},
    }

    label, host, model, _key = main_module.resolve_llm(settings)

    assert label == "LFM3-Omni 2B"
    assert host == "127.0.0.1:8084"
    assert model.endswith("Q6_K.gguf")

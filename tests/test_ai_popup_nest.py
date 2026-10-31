"""Tests for the Nest-based main file (``ai-popup.py``), the migration target.

The contract that matters while the old package is still being absorbed: the
module imports without a running app, sending is gated on backend state, message
IDs stay unique, backend selection follows the saved settings, and replies stream
from an OpenAI-compatible server.
"""
from __future__ import annotations

import base64
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
    assert hasattr(main_module, "PopupController")
    assert hasattr(main_module, "NestView")
    assert hasattr(main_module.NestView, "send_requested")


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


def test_notices_reuse_their_id_instead_of_raising(app, main_module):
    view = main_module.NestView()
    view.add_notice("capture failed", "notice-1")
    view.add_notice("capture failed again", "notice-1")
    assert view._messages["notice-1"].text() == "capture failed again"


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

    answer = main_module.stream_chat("127.0.0.1:1", "m", [], seen.append)

    assert answer == "Hello!"
    assert seen == ["Hel", "lo", "!"]


def test_cancelled_stream_stops_early(monkeypatch, main_module):
    import threading

    class _Response:
        headers = {"Content-Type": "text/event-stream"}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def __iter__(self):
            for piece in ("a", "b", "c"):
                yield f"data: {json.dumps({'choices': [{'delta': {'content': piece}}]})}\n".encode()

    cancel = threading.Event()
    seen: list[str] = []

    def _on_delta(piece):
        seen.append(piece)
        cancel.set()  # the first token already cancels, like Esc during a reply

    monkeypatch.setattr(main_module.urllib.request, "urlopen", lambda *a, **k: _Response())

    assert main_module.stream_chat("127.0.0.1:1", "m", [], _on_delta, cancel) == "a"
    assert seen == ["a"]


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

    assert main_module.stream_chat("127.0.0.1:1", "m", []) == "plain"


def test_resolve_target_prefers_lfm3_when_weights_are_configured(main_module):
    settings = {"lfm3": {"gguf_path": "/models/LFM3-Omni-2B-Abliter8-Q6_K.gguf", "host": "127.0.0.1:8084"}}

    target = main_module.resolve_target(settings)

    assert target.key == "lfm3"
    assert target.label == "LFM3-Omni 2B"
    assert target.host == "127.0.0.1:8084"
    assert target.model.endswith("Q6_K.gguf")
    assert target.configured


def test_resolve_target_honours_an_explicit_voice_profile(main_module):
    settings = {
        "lfm3": {"gguf_path": "/models/LFM3-Omni-2B-Abliter8-Q6_K.gguf"},
        "koboldcpp": {"gguf_path": "/models/other.gguf", "host": "127.0.0.1:5001"},
        "_voice_mode": {"llm_profile": "koboldcpp"},
    }

    target = main_module.resolve_target(settings)

    assert target.key == "koboldcpp"
    assert target.host == "127.0.0.1:5001"


def test_resolve_target_falls_back_to_the_default_host(main_module):
    target = main_module.resolve_target({"lfm3": {"gguf_path": "/models/model.gguf"}})
    assert target.host == "127.0.0.1:8082"


def test_unconfigured_settings_report_not_configured(main_module):
    target = main_module.resolve_target({})
    assert not target.configured
    assert target.key == ""


def test_build_messages_attaches_images_as_data_urls(main_module, tmp_path):
    image = tmp_path / "shot.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfake")

    messages = main_module.build_messages("what is this?", [image], [{"role": "user", "content": "prev"}])

    assert [m["role"] for m in messages] == ["system", "user", "user"]
    parts = messages[-1]["content"]
    assert isinstance(parts, list)
    assert parts[0]["text"] == "what is this?"
    expected = "data:image/png;base64," + base64.b64encode(image.read_bytes()).decode()
    assert parts[1]["image_url"]["url"] == expected


def test_build_messages_inlines_text_attachments(main_module, tmp_path):
    note = tmp_path / "notes.txt"
    note.write_text("remember the milk")

    messages = main_module.build_messages("read this", [note], [])

    assert isinstance(messages[-1]["content"], str)
    assert "remember the milk" in messages[-1]["content"]


def test_state_dir_honours_the_environment_override(monkeypatch, main_module, tmp_path):
    monkeypatch.setenv("HANAUTA_AI_STATE_DIR", str(tmp_path / "state"))
    assert main_module.state_dir() == tmp_path / "state"
    assert main_module.state_dir().is_dir()


def test_encrypted_history_and_secrets_round_trip(monkeypatch, main_module, tmp_path):
    monkeypatch.setenv("HANAUTA_AI_STATE_DIR", str(tmp_path))

    main_module.append_history("user", "hello")
    main_module.append_history("assistant", "hi there")
    main_module.store_secret("demo", "s3cret")

    assert main_module.load_history() == [("user", "hello"), ("assistant", "hi there")]
    assert main_module.load_secret("demo") == "s3cret"
    # Same file names the legacy package used, so old history stays readable.
    assert (tmp_path / "secure_store.sqlite3").exists()
    assert (tmp_path / "secure_store.key").exists()
    raw = (tmp_path / "secure_store.sqlite3").read_bytes()
    assert b"hello" not in raw  # payloads are encrypted, not plain text


def test_open_settings_uses_the_native_dialog(monkeypatch, app, main_module, tmp_path):
    """Regression: opening settings must not raise (it once aborted the app)."""
    monkeypatch.setenv("HANAUTA_AI_STATE_DIR", str(tmp_path))
    (tmp_path / "backend_settings.json").write_text(
        json.dumps({"lfm3": {"gguf_path": "/models/model.gguf", "host": "127.0.0.1:8082"}})
    )
    captured: dict[str, object] = {}

    class _StubDialog:
        def __init__(self, settings, theme, parent=None):
            captured["settings"] = settings
            captured["theme"] = theme

        def exec(self):
            captured["exec"] = True
            return 0

    monkeypatch.setattr(main_module, "SettingsDialog", _StubDialog)
    window = main_module.PopupController()
    window.open_settings()

    assert captured["exec"] is True
    assert "lfm3" in captured["settings"]
    window.close()


def test_main_file_no_longer_depends_on_the_legacy_settings_dialog(main_module):
    source = (ROOT / "ai-popup.py").read_text(encoding="utf-8")
    assert "ui_backend_settings" not in source
    assert hasattr(main_module, "SettingsDialog")


def test_settings_dialog_saves_through_the_absorbed_view(app, main_module, monkeypatch, tmp_path):
    monkeypatch.setenv("HANAUTA_AI_STATE_DIR", str(tmp_path))
    settings = {
        "lfm3": {"gguf_path": "/models/model.gguf", "host": "127.0.0.1:8082"},
        "_voice_mode": {"token_saver_enabled": False},
    }
    dialog = main_module.SettingsDialog(settings, main_module.Theme(), None)
    assert dialog.backend_key() == "lfm3"
    assert dialog.view.backend.currentData() == "lfm3"

    dialog.view.fields["endpoint"].setText("127.0.0.1:9090")
    dialog.view.fields["mmproj_path"].setText("/models/mmproj.gguf")
    dialog.view.fields["parameter_2"].setValue(4096)
    dialog.view.compute.setCurrentText("GPU")
    dialog.view.token_saver.setChecked(True)
    dialog._save(dialog.view.values())

    saved = json.loads((tmp_path / "backend_settings.json").read_text())
    assert saved["lfm3"]["host"] == "127.0.0.1:9090"
    assert saved["lfm3"]["gguf_path"] == "/models/model.gguf"  # untouched keys survive
    assert saved["lfm3"]["mmproj_path"] == "/models/mmproj.gguf"  # required for audio input
    assert saved["lfm3"]["llama_context"] == "4096"
    assert saved["lfm3"]["device"] == "gpu"
    assert saved["_voice_mode"]["token_saver_enabled"] is True


def test_settings_view_lists_the_configured_backends(app, main_module, monkeypatch, tmp_path):
    monkeypatch.setenv("HANAUTA_AI_STATE_DIR", str(tmp_path))
    settings = {
        "lfm3": {"gguf_path": "/models/a.gguf"},
        "koboldcpp": {"gguf_path": "/models/b.gguf", "host": "127.0.0.1:5001"},
    }
    dialog = main_module.SettingsDialog(settings, main_module.Theme(), None)
    options = [dialog.view.backend.itemData(i) for i in range(dialog.view.backend.count())]
    assert options == ["lfm3", "koboldcpp"]

    dialog.view.backend.setCurrentIndex(1)
    assert dialog.view.fields["endpoint"].text() == "127.0.0.1:5001"


def test_asr_goes_to_lfm3_as_an_audio_part(main_module, tmp_path):
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"RIFFwavdata")
    request = main_module.asr_request("lfm3", base64.b64encode(audio.read_bytes()).decode(), "English")

    assert request["messages"][0]["content"][0]["text"].startswith("Perform ASR in English")
    audio_part = request["messages"][0]["content"][1]
    assert audio_part["type"] == "input_audio"
    assert audio_part["input_audio"]["format"] == "wav"
    assert base64.b64decode(audio_part["input_audio"]["data"]) == b"RIFFwavdata"


def test_transcribe_audio_reads_the_reply(monkeypatch, main_module, tmp_path):
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"RIFF")

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "  hello there \n"}}]}).encode()

    monkeypatch.setattr(main_module.urllib.request, "urlopen", lambda *a, **k: _Response())

    assert main_module.transcribe_audio(audio, "127.0.0.1:8082", "lfm3") == "hello there"


def test_speech_tooling_is_gone_from_the_popup(main_module):
    source = (ROOT / "ai-popup.py").read_text(encoding="utf-8")
    for needle in ("transcribe_voice_audio", "synthesize_tts", "faster_whisper", "_voice_mode_settings"):
        assert needle not in source
    assert hasattr(main_module, "transcribe_audio")


def test_build_server_command_matches_the_lfm3_serving_flags(main_module, tmp_path):
    binary = tmp_path / "llama-server"
    binary.write_text("#!/bin/sh\n")
    model = tmp_path / "LFM3-Omni-2B-Abliter8-Q6_K.gguf"
    model.write_bytes(b"gguf")
    mmproj = tmp_path / "mmproj.gguf"
    mmproj.write_bytes(b"gguf")

    command = main_module.build_server_command(
        {
            "gguf_path": str(model),
            "mmproj_path": str(mmproj),
            "host": "127.0.0.1:8082",
            "llama_context": "8192",
            "llama_flash_attn": True,
            "device": "gpu",
        },
        binary,
        model,
    )

    assert command[:3] == [str(binary), "-m", str(model)]
    assert command[command.index("-c") + 1] == "8192"
    assert command[command.index("--mmproj") + 1] == str(mmproj)
    assert command[command.index("--host") + 1] == "127.0.0.1"
    assert command[command.index("--port") + 1] == "8082"
    assert "--jinja" in command
    # LFM3 is a non-reasoning architecture and its build wants a value for flash-attn.
    assert command[command.index("--reasoning") + 1] == "off"
    assert command[command.index("--flash-attn") + 1] == "on"
    assert command[command.index("--gpu-layers") + 1] == "99"


def test_build_server_command_drops_a_missing_mmproj(main_module, tmp_path):
    binary = tmp_path / "llama-server"
    model = tmp_path / "qwen2.5-3b-instruct-q4_k_m.gguf"
    model.write_bytes(b"gguf")

    command = main_module.build_server_command(
        {"mmproj_path": str(tmp_path / "gone.gguf"), "llama_reasoning_off": False}, binary, model
    )

    assert "--mmproj" not in command
    assert "--reasoning" not in command  # only LFM3 defaults it off
    assert "--flash-attn" not in command


def test_launch_server_refuses_when_no_runtime_exists(monkeypatch, main_module, tmp_path):
    monkeypatch.setattr(main_module, "bundled_llama_server", lambda: None)

    ok, message = main_module.launch_server({"gguf_path": str(tmp_path / "model.gguf")})
    assert not ok and "llama-server" in message.lower()


def test_launch_server_adopts_the_bundled_runtime(monkeypatch, main_module, tmp_path):
    binary = tmp_path / "llama-server"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    model = tmp_path / "LFM3-Omni-2B-Abliter8-Q6_K.gguf"
    model.write_bytes(b"gguf")
    seen: dict = {}

    class _FakeProcess:
        pid = 4242

    def _fake_popen(command, **kwargs):
        seen["command"] = command
        return _FakeProcess()

    monkeypatch.setattr(main_module, "bundled_llama_server", lambda: binary)
    monkeypatch.setattr(main_module.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(main_module.os, "getpgid", lambda pid: pid)

    payload = {"gguf_path": str(model), "host": "127.0.0.1:8082"}
    ok, message = main_module.launch_server(payload)

    assert ok, message
    assert payload["binary_path"] == str(binary)
    assert seen["command"][0] == str(binary)
    assert str(model) in seen["command"]


def test_settings_show_the_bundled_binary(main_module, monkeypatch, tmp_path):
    binary = tmp_path / "llama-server"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    monkeypatch.setattr(main_module, "bundled_llama_server", lambda: binary)

    values = main_module.settings_values({"lfm3": {"gguf_path": "/models/model.gguf"}}, "lfm3")

    assert values["executable"] == str(binary)


def test_bundled_runtime_resolves_to_an_executable(main_module):
    bundled = main_module.bundled_llama_server()
    assert bundled is None or (bundled.name == "llama-server" and bundled.is_file())


def test_busy_port_moves_the_server_to_a_free_one(monkeypatch, main_module, tmp_path):
    import socket

    binary = tmp_path / "llama-server"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    model = tmp_path / "LFM3-Omni-2B-Abliter8-Q6_K.gguf"
    model.write_bytes(b"gguf")

    held = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    held.bind(("127.0.0.1", 0))
    held.listen(1)
    busy_port = held.getsockname()[1]
    seen: dict = {}

    class _FakeProcess:
        pid = 777

    monkeypatch.setattr(main_module, "bundled_llama_server", lambda: binary)
    monkeypatch.setattr(
        main_module.subprocess,
        "Popen",
        lambda command, **kwargs: (seen.setdefault("command", command), _FakeProcess())[1],
    )
    monkeypatch.setattr(main_module.os, "getpgid", lambda pid: pid)

    try:
        payload = {"gguf_path": str(model), "host": f"127.0.0.1:{busy_port}"}
        ok, message = main_module.launch_server(payload)
    finally:
        held.close()

    assert ok, message
    assert "moved to" in message
    new_port = int(payload["host"].rsplit(":", 1)[1])
    assert new_port != busy_port
    assert seen["command"][seen["command"].index("--port") + 1] == str(new_port)


def test_stop_server_reports_untracked_and_stale_processes(main_module):
    payload: dict = {}
    ok, message = main_module.stop_server(payload)
    assert not ok and "no tracked" in message.lower()

    dead = {"llamacpp_pid": 999_999_999, "llamacpp_pgid": 999_999_999}
    ok, message = main_module.stop_server(dead)
    assert not ok and "already stopped" in message.lower()
    assert dead["llamacpp_pid"] == 0 and dead["llamacpp_pgid"] == 0


def test_entry_guard_is_the_last_statement():
    """Regression: pages appended after the guard made `python ai-popup.py` raise NameError."""
    import ast

    tree = ast.parse((ROOT / "ai-popup.py").read_text(encoding="utf-8"))
    last = tree.body[-1]
    assert isinstance(last, ast.If), "the __main__ guard must be last so every class exists before main() runs"
    guard = ast.unparse(last.test)
    assert "__name__" in guard and "'__main__'" in guard.replace('"', "'")


def test_start_backend_reuses_a_running_server(monkeypatch, app, main_module, tmp_path):
    monkeypatch.setenv("HANAUTA_AI_STATE_DIR", str(tmp_path))
    (tmp_path / "backend_settings.json").write_text(
        json.dumps({"lfm3": {"gguf_path": "/models/model.gguf", "host": "127.0.0.1:8123"}})
    )
    calls: list[str] = []
    monkeypatch.setattr(main_module, "_probe", lambda host: True)
    monkeypatch.setattr(main_module, "stop_server", lambda payload: (calls.append("stop"), (True, "stopped"))[1])
    monkeypatch.setattr(main_module, "launch_server", lambda payload: (calls.append("launch"), (True, "ok"))[1])

    controller = main_module.PopupController()
    try:
        controller.start_backend()
    finally:
        controller.close()

    assert calls == []  # a live backend is never restarted or stopped by Start


def test_entry_launcher_loads_the_new_main_file():
    sys.path.insert(0, str(ROOT))
    import ai_popup

    module = ai_popup.load_main()
    assert hasattr(module, "PopupController")
    assert module.__name__ == "hanauta_popup_main"


# -- voice stage (holographic portrait) + personalities -------------------- #


def _write_pcm_wav(path: Path, amplitudes: list[float], rate: int = 8000) -> Path:
    """Write a 16-bit mono WAV: one 0.5 s block per amplitude in 0..1."""
    import array
    import wave

    values = array.array("h")
    for amplitude in amplitudes:
        samples = int(rate * 0.5)
        values.extend(int(amplitude * 30000) * (1 if index % 2 == 0 else -1) for index in range(samples))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(values.tobytes())
    return path


def test_parse_visemes_accepts_rhubarb_cues(main_module):
    cues = main_module.parse_visemes(
        {
            "mouthCues": [
                {"start": 0.0, "end": 0.1, "value": "A"},
                {"start": 0.1, "end": 0.3, "value": "d"},
                {"start": 0.3, "end": 0.4, "value": "X"},
            ]
        }
    )
    assert cues == [(0.0, 0.1, "A"), (0.1, 0.3, "D"), (0.3, 0.4, "X")]


def test_parse_visemes_rejects_bad_cues(main_module):
    with pytest.raises(ValueError):
        main_module.parse_visemes(
            [
                {"start": 0.0, "end": 0.3, "value": "A"},
                {"start": 0.2, "end": 0.4, "value": "D"},
            ]
        )
    with pytest.raises(ValueError):
        main_module.parse_visemes([{"start": 0.0, "end": 0.1, "value": "Z"}])
    with pytest.raises(ValueError):
        main_module.parse_visemes([{"start": 0.4, "end": 0.2, "value": "A"}])


def test_viseme_sidecar_sits_next_to_the_clip(main_module, tmp_path):
    clip = tmp_path / "speech_1.wav"
    clip.write_bytes(b"RIFF")
    (tmp_path / "speech_1.json").write_text(
        json.dumps({"mouthCues": [{"start": 0.0, "end": 0.2, "value": "B"}]}), encoding="utf-8"
    )
    assert main_module.viseme_cues_for(clip) == [(0.0, 0.2, "B")]

    (tmp_path / "speech_1.json").write_text("{not json", encoding="utf-8")
    assert main_module.viseme_cues_for(clip) == []
    assert main_module.viseme_cues_for(tmp_path / "missing.wav") == []


def test_wav_envelope_follows_loudness(main_module, tmp_path):
    clip = _write_pcm_wav(tmp_path / "clip.wav", [0.9, 0.9, 0.0, 0.0])
    levels = main_module.wav_envelope(clip)
    assert max(levels[:5]) > 0.9
    assert max(levels[-5:]) == 0.0


def test_voice_stage_builds_the_portrait_and_timed_visemes(app, main_module):
    stage = main_module.VoiceStage()
    try:
        assert not stage.face._still.isNull()
        try:
            import numpy  # noqa: F401
        except Exception:
            assert not stage.face.lipsync_ready  # the portrait still shows, statically
        else:
            assert stage.face.lipsync_ready

        stage.set_visemes({"mouthCues": [{"start": 0.0, "end": 1.0, "value": "D"}]})
        assert stage.current_viseme(0.5) == "D"
        assert stage.current_viseme(1.5) is None
        stage.set_voice_frame(0.8, "D")
    finally:
        stage.stop()


def test_face_canvas_warps_a_frame(app, main_module):
    pytest.importorskip("numpy")
    canvas = main_module.FaceCanvas()
    canvas.set_level(1.0, "D")
    frame = canvas._warp(1.0)
    assert not frame.isNull()
    assert frame.size().width() == canvas.WIDTH


def test_voice_stage_controls_reach_the_controller(monkeypatch, app, main_module, tmp_path):
    monkeypatch.setenv("HANAUTA_AI_STATE_DIR", str(tmp_path))
    (tmp_path / "backend_settings.json").write_text(
        json.dumps({"lfm3": {"gguf_path": "/models/model.gguf", "host": "127.0.0.1:8123"}})
    )
    controller = main_module.PopupController()
    try:
        captured: list[tuple[str, bool]] = []
        monkeypatch.setattr(
            controller, "capture_frame", lambda kind, chime=False: captured.append((kind, chime))
        )
        shares: list[str] = []
        monkeypatch.setattr(controller, "toggle_share", lambda kind: shares.append(kind))

        stage = controller.open_voice_stage()
        # Voice mode is a page in the same window, not a second window.
        assert controller.stack.currentWidget() is stage
        assert stage.window() is controller

        stage.action("capture")
        assert captured == [("screen", True)]

        stage.toggle_context()
        assert shares == ["screen"]

        stage.action("close")
        assert controller.stack.currentWidget() is controller.view
    finally:
        controller.shutdown()


def test_speech_engine_lfm3_uses_liquidcodec(main_module, monkeypatch, tmp_path):
    monkeypatch.setenv("HANAUTA_AI_STATE_DIR", str(tmp_path))
    clip = tmp_path / "lfm3.wav"
    clip.write_bytes(b"RIFF")
    seen: dict = {}

    def fake(text, config):
        seen["text"] = text
        return clip

    monkeypatch.setattr(main_module, "synthesize_lfm3_speech", fake)
    assert main_module.synthesize_speech("hello there", {"tts_backend": "lfm3"}) == clip
    assert seen["text"] == "hello there"


def test_lfm3_failure_respects_the_fallback_switch(main_module, monkeypatch, tmp_path):
    monkeypatch.setenv("HANAUTA_AI_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(main_module, "synthesize_lfm3_speech", lambda text, config: None)
    monkeypatch.setattr(main_module.shutil, "which", lambda name: None)
    assert main_module.synthesize_speech(
        "hi", {"tts_backend": "lfm3", "tts_fallback": False}
    ) is None


def test_lfm3_helper_uses_the_documented_speech_api(main_module):
    source = main_module.LFM3_VOICE_HELPER
    for needle in (
        "Perform TTS in",
        'generation_mode="audio"',
        "audio_tokenizer",
        "codec.decode",
        "24_000",
        "audio_temperature=0.4",
    ):
        assert needle in source


def test_lfm3_voice_command_uses_its_own_venv(monkeypatch, main_module, tmp_path):
    monkeypatch.setenv("HANAUTA_AI_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(main_module, "lfm3_voice_dir", lambda: tmp_path / "venv")
    fake = tmp_path / "venv" / "bin" / "python"
    fake.parent.mkdir(parents=True)
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)

    command = main_module.Lfm3Voice().command()
    assert command[0] == str(fake)
    assert command[command.index("--model") + 1] == main_module.LFM3_VOICE_MODEL
    assert Path(command[1]).is_file()
    assert main_module.lfm3_voice_ready() is False


def test_lfm3_voice_helper_protocol_round_trip(monkeypatch, main_module, tmp_path):
    """The helper speaks JSON over stdin/stdout; verify the pipe, not the model."""
    state = tmp_path / "state"
    monkeypatch.setenv("HANAUTA_AI_STATE_DIR", str(state))
    out_dir = state / "voice-tts"
    helper = tmp_path / "fake_helper.py"
    helper.write_text(
        "import json, sys, time\n"
        "from pathlib import Path\n"
        "out = Path(sys.argv[sys.argv.index('--out-dir') + 1])\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "for line in sys.stdin:\n"
        "    request = json.loads(line)\n"
        "    target = out / ('fake_' + str(int(time.time_ns())) + '.wav')\n"
        "    target.write_bytes(b'RIFF' + request['text'].encode())\n"
        "    print(json.dumps({'path': str(target)}), flush=True)\n",
        encoding="utf-8",
    )
    engine = main_module.Lfm3Voice()
    monkeypatch.setattr(
        engine, "command", lambda: [sys.executable, str(helper), "--out-dir", str(out_dir)]
    )
    try:
        clip = engine.synthesize("hello there", "American English", "female", timeout=30)
    finally:
        engine.close()

    assert clip is not None and clip.is_file()
    assert b"hello there" in clip.read_bytes()


def test_voice_page_offers_and_saves_the_lfm3_engine(monkeypatch, app, main_module, tmp_path):
    monkeypatch.setenv("HANAUTA_AI_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(main_module, "lfm3_voice_dir", lambda: tmp_path / "venv")
    page = main_module.VoicePage({"lfm3": {"gguf_path": "/models/model.gguf"}})
    engines = [page.backend.itemText(i) for i in range(page.backend.count())]
    assert "lfm3" in engines

    page.backend.setCurrentText("lfm3")
    index = page.lfm3_language.findText("British English")
    page.lfm3_language.setCurrentIndex(index)
    page.lfm3_gender.setCurrentText("male")
    page.fallback.setChecked(False)
    page.save()

    saved = json.loads((tmp_path / "backend_settings.json").read_text(encoding="utf-8"))["_voice_mode"]
    assert saved["tts_backend"] == "lfm3"
    assert saved["tts_lfm3_language"] == "British English"
    assert saved["tts_lfm3_gender"] == "male"
    assert saved["tts_fallback"] is False
    assert "LFM3" in page.lfm3_status.text()
    assert page.prepare.isEnabled() is True  # the runtime is not installed yet


def test_settings_save_persists_runtime_toggles(monkeypatch, app, main_module, tmp_path):
    """Regression: checking Flash Attention / MTP then Save left them unchecked."""
    monkeypatch.setenv("HANAUTA_AI_STATE_DIR", str(tmp_path))
    (tmp_path / "backend_settings.json").write_text(
        json.dumps({"lfm3": {"gguf_path": "/models/model.gguf", "host": "127.0.0.1:8123"}})
    )

    dialog = main_module.SettingsDialog(main_module.load_settings(), main_module.Theme())
    dialog.view.flash.setChecked(True)
    dialog.view.mtp.setChecked(True)
    dialog.view.compute.setCurrentText("GPU")
    dialog._save(dialog.view.values())
    dialog.close()

    saved = json.loads((tmp_path / "backend_settings.json").read_text(encoding="utf-8"))["lfm3"]
    assert saved["llama_flash_attn"] is True
    assert saved["llama_mtp_enabled"] is True
    assert saved["device"] == "gpu"

    reopened = main_module.SettingsDialog(main_module.load_settings(), main_module.Theme())
    assert reopened.view.flash.isChecked()
    assert reopened.view.mtp.isChecked()
    assert reopened.view.compute.currentText() == "GPU"
    reopened.close()


def test_voice_page_saves_engine_voice_and_barge_in(monkeypatch, app, main_module, tmp_path):
    monkeypatch.setenv("HANAUTA_AI_STATE_DIR", str(tmp_path))
    page = main_module.VoicePage({"lfm3": {"gguf_path": "/models/model.gguf"}})
    assert page.voices.count() > 1

    index = page.voices.findData("en+m3")
    assert index >= 0
    page.voices.setCurrentIndex(index)
    page.speed.setValue(180)
    page.barge.setChecked(True)
    page.speak.setChecked(True)
    page.save()

    saved = json.loads((tmp_path / "backend_settings.json").read_text(encoding="utf-8"))["_voice_mode"]
    assert saved["tts_enabled"] is True
    assert saved["tts_backend"] == "espeak"
    assert saved["tts_voice"] == "en+m3"
    assert saved["tts_speed"] == "180"
    assert saved["barge_in_enabled"] is True


def test_speech_is_on_by_default_and_barge_in_is_opt_in(main_module):
    assert main_module.VOICE_DEFAULTS["tts_enabled"] is True
    assert main_module.VOICE_DEFAULTS["barge_in_enabled"] is False
    # espeak is never substituted silently for LFM3's voice
    assert main_module.VOICE_DEFAULTS["tts_fallback"] is False


def test_lfm3_tts_command_matches_the_model_card(main_module, tmp_path):
    binary = tmp_path / "llama-tts"
    model = tmp_path / "model.gguf"
    mmproj = tmp_path / "mmproj.gguf"
    output = tmp_path / "out.wav"

    command = main_module.lfm3_tts_command(
        binary,
        model,
        mmproj,
        "Hello world",
        output,
        {"tts_lfm3_language": "British English", "tts_lfm3_gender": "male"},
    )

    assert command[:5] == [str(binary), "-m", str(model), "-mm", str(mmproj)]
    assert command[command.index("-p") + 1] == "Hello world"
    assert command[command.index("-o") + 1] == str(output)
    assert command[command.index("--tts-lang") + 1] == "en"
    assert command[command.index("--tts-voice") + 1] == "male"

    no_projector = main_module.lfm3_tts_command(binary, model, None, "hi", output, {})
    assert "-mm" not in no_projector
    assert no_projector[no_projector.index("--tts-voice") + 1] == "female"


def test_lfm3_tts_prefers_the_native_tool(monkeypatch, main_module, tmp_path):
    monkeypatch.setenv("HANAUTA_AI_STATE_DIR", str(tmp_path / "state"))
    reference = _write_pcm_wav(tmp_path / "reference.wav", [0.8, 0.8])
    binary = tmp_path / "llama-tts"
    binary.write_text(
        "#!/bin/sh\nout=\"\"\nwhile [ $# -gt 0 ]; do\n"
        "  if [ \"$1\" = \"-o\" ]; then out=\"$2\"; shift 2; else shift; fi\ndone\n"
        + f"cp '{reference}' \"$out\"\n",
        encoding="utf-8",
    )
    binary.chmod(0o755)
    model = tmp_path / "model.gguf"
    model.write_bytes(b"gguf")

    monkeypatch.setattr(main_module, "bundled_llama_tts", lambda: binary)
    monkeypatch.setattr(
        main_module, "load_settings", lambda: {"lfm3": {"gguf_path": str(model), "host": "127.0.0.1:8082"}}
    )

    clip = main_module.synthesize_lfm3_speech(
        "hello there", {"tts_lfm3_language": "American English", "tts_lfm3_gender": "female"}
    )
    assert clip is not None
    assert main_module.wav_rms(clip) > 0


def test_voice_engine_migrates_from_espeak_once(main_module):
    settings = {"_voice_mode": {"tts_backend": "espeak"}}
    assert main_module.migrate_voice_engine(settings) is True
    assert settings["_voice_mode"]["tts_backend"] == "lfm3"
    assert settings["_voice_mode"]["tts_fallback"] is False

    assert main_module.migrate_voice_engine(settings) is False
    custom = {"_voice_mode": {"tts_backend": "piper", "tts_engine_migrated": True}}
    assert main_module.migrate_voice_engine(custom) is False


def test_bundled_llama_tts_resolves_or_none(main_module):
    binary = main_module.bundled_llama_tts()
    assert binary is None or (binary.name == "llama-tts" and binary.is_file())


def test_espeak_voices_are_english_codes(main_module):
    voices = main_module.espeak_voices()
    codes = [code for code, _label in voices]
    assert "en+f3" in codes
    assert all(code.startswith("en") for code in codes)
    assert len(codes) == len(set(codes))


def test_phonemes_become_timed_visemes(main_module):
    cues = main_module.visemes_from_phonemes("p'aI_l'aU t'Est", 2.0)
    assert cues and cues[0][0] == 0.0
    assert cues[-1][1] >= 1.99
    assert all(start < end for start, end, _value in cues)
    assert all(value in main_module.VISEMES for _start, _end, value in cues)

    # adjacent identical mouth shapes merge instead of flickering
    assert len(main_module.visemes_from_phonemes("p b m", 1.0)) == 1
    assert [viseme for viseme, _weight in main_module.phoneme_visemes("tSaI")] == ["B", "D"]
    assert main_module.visemes_from_phonemes("", 1.0) == []
    assert main_module.visemes_from_phonemes("pa", 0) == []


def test_persona_selects_a_tts_voice(main_module):
    assert main_module.speech_config({"personality": "waifu"})["tts_voice"] == "en+f3"
    explicit = main_module.speech_config(
        {"personality": "waifu", "tts_voice": "en+m1", "tts_speed": "150"}
    )
    assert explicit["tts_voice"] == "en+m1"
    assert explicit["tts_speed"] == "150"
    assert main_module.speech_config({"personality": "default"}).get("tts_voice", "") == ""


def test_synthesize_speech_attaches_phoneme_visemes(main_module, monkeypatch, tmp_path):
    import shutil as _shutil

    if not (_shutil.which("espeak-ng") or _shutil.which("espeak")):
        pytest.skip("espeak is not installed")
    monkeypatch.setenv("HANAUTA_AI_STATE_DIR", str(tmp_path))

    clip = main_module.synthesize_speech("Hello there, testing lip sync.", {"tts_backend": "espeak"})
    assert clip is not None
    cues = main_module.viseme_cues_for(clip)
    assert cues and cues[0][0] == 0.0
    assert cues[-1][1] > 0.5
    assert all(value in main_module.VISEMES for _start, _end, value in cues)


def test_stage_persona_picker_persists_the_choice(monkeypatch, app, main_module, tmp_path):
    monkeypatch.setenv("HANAUTA_AI_STATE_DIR", str(tmp_path))
    (tmp_path / "backend_settings.json").write_text(
        json.dumps({"lfm3": {"gguf_path": "/models/model.gguf", "host": "127.0.0.1:8123"}})
    )
    controller = main_module.PopupController()
    try:
        stage = controller.open_voice_stage()
        index = stage.persona.findData("coach")
        assert index >= 0
        stage.persona.setCurrentIndex(index)

        saved = json.loads((tmp_path / "backend_settings.json").read_text(encoding="utf-8"))
        assert saved["_voice_mode"]["personality"] == "coach"
        assert "coach" in main_module.compose_system_prompt().lower()
    finally:
        controller.shutdown()


def test_personality_is_injected_into_the_system_prompt(monkeypatch, main_module, tmp_path):
    monkeypatch.setenv("HANAUTA_AI_STATE_DIR", str(tmp_path))
    for key in ("waifu", "psychologist", "coach", "custom"):
        assert key in main_module.PERSONALITY_PRESETS

    coach = main_module.compose_system_prompt({"_voice_mode": {"personality": "coach"}})
    assert "coach" in coach.lower()

    custom = main_module.compose_system_prompt(
        {"_voice_mode": {"personality": "custom", "personality_prompt": "Speak like a pirate."}}
    )
    assert "pirate" in custom
    assert "pirate" not in main_module.compose_system_prompt({"_voice_mode": {"personality": "default"}})

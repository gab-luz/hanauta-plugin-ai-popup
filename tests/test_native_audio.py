"""Tests for sending recorded audio to the model as an input_audio part."""
import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hanauta_aipopup import tts  # noqa: E402


def _wav(path: Path, frames: int = 800) -> Path:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * frames)
    return path


def test_audio_part_shape(tmp_path):
    part = tts._audio_input_part(_wav(tmp_path / "a.wav"))
    assert part["type"] == "input_audio"
    inner = part["input_audio"]
    assert inner["format"] == "wav"
    assert inner["data"], "audio bytes should be base64 encoded"


def test_empty_audio_file_is_rejected(tmp_path):
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    with pytest.raises(RuntimeError):
        tts._audio_input_part(empty)


def test_audio_part_lands_in_the_user_message(tmp_path):
    part = tts._audio_input_part(_wav(tmp_path / "a.wav"))
    messages = tts._chat_messages_with_memory("hi", None, extra_parts=[part])
    content = messages[-1]["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert part in content


def test_audio_and_image_parts_coexist(tmp_path):
    part = tts._audio_input_part(_wav(tmp_path / "a.wav"))
    messages = tts._chat_messages_with_memory(
        "hi", None, images=["data:image/jpeg;base64,AAA"], extra_parts=[part]
    )
    kinds = [p["type"] for p in messages[-1]["content"]]
    assert kinds[0] == "text"
    assert "image_url" in kinds
    assert "input_audio" in kinds


def test_native_audio_defaults_to_off():
    from hanauta_aipopup.voice import _voice_mode_defaults

    assert _voice_mode_defaults()["native_audio_input"] is False


def test_no_audio_keeps_plain_content(tmp_path):
    messages = tts._chat_messages_with_memory("hi", None, extra_parts=[])
    assert isinstance(messages[-1]["content"], str)

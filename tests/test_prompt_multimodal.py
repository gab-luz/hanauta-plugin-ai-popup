"""Tests for multimodal prompt assembly."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hanauta_aipopup import tts  # noqa: E402

IMAGE_URL = "data:image/jpeg;base64,AAAA"


def test_text_only_prompt_keeps_string_content():
    messages = tts._chat_messages_with_memory("hello", None)
    assert isinstance(messages[-1]["content"], str)
    assert messages[-1]["content"] == "hello"


def test_image_produces_multimodal_content():
    messages = tts._chat_messages_with_memory("what do you see?", None, images=[IMAGE_URL])
    content = messages[-1]["content"]
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "what do you see?"}
    assert {"type": "image_url", "image_url": {"url": IMAGE_URL}} in content


def test_system_message_stays_a_string():
    messages = tts._chat_messages_with_memory("hi", None, images=[IMAGE_URL])
    assert messages[0]["role"] == "system"
    assert isinstance(messages[0]["content"], str)


def test_memory_is_inserted_after_system_prompt():
    messages = tts._chat_messages_with_memory("hi", None, memory="User likes tea.")
    assert messages[1]["role"] == "system"
    assert "User likes tea." in messages[1]["content"]


def test_empty_image_list_behaves_like_text_only():
    messages = tts._chat_messages_with_memory("hi", None, images=[])
    assert isinstance(messages[-1]["content"], str)

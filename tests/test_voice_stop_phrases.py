"""Regression tests for voice stop phrases.

These phrases were silently dead: `VOICE_STOP_EXPRESSIONS_FILE` was undefined in
tts.py, the resulting NameError was swallowed, and the payload was always empty,
so hands-free voice mode could never be stopped by voice.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hanauta_aipopup import tts  # noqa: E402


def test_stop_expressions_load_from_shipped_file():
    payload = tts._load_voice_stop_expressions()
    assert payload, "stop expressions should load from voice-stop-expressions.json"
    assert sum(len(values) for values in payload.values()) > 0


def test_shipped_phrase_matches():
    assert tts._matches_stop_phrase("hanauta stop", {}) is True


def test_longer_phrase_with_prefix_matches():
    assert tts._matches_stop_phrase("hanauta stop listening", {}) is True


def test_unrelated_speech_does_not_match():
    assert tts._matches_stop_phrase("what is the weather like today", {}) is False


def test_normalize_strips_punctuation_and_case():
    assert tts._normalize_stop_text("Hanauta, stop!") == "hanauta stop"


def test_disabled_stop_phrases_never_match():
    assert tts._matches_stop_phrase("hanauta stop", {"stop_phrases_enabled": False}) is False

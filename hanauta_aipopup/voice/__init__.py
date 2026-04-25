# Voice mode: recording, STT, voice defaults
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

from hanauta_aipopup.runtime import (
    AI_STATE_DIR,
    VOICE_PRIVACY_CODEBOOK_FILE,
    VOICE_RECORDINGS_DIR,
    VOICE_STOP_EXPRESSIONS_FILE,
)


def _safe_slug(value: str) -> str:
    return "_".join(p for p in value.translate({ord(c): "_" for c in " -"}).split("_") if p)[:80] or "audio"


def _voice_mode_defaults() -> dict:
    return {
        "enabled": False,
        "record_seconds": "5",
        "silence_threshold": "0.012",
        "eos_adaptive_enabled": True,
        "eos_noise_margin": "0.004",
        "eos_hysteresis": "0.82",
        "speech_end_silence_ms": "750",
        "listen_chunk_seconds": "0.75",
        "min_speech_ms": "260",
        "stt_backend": "whisper",
        "stt_model": "small",
        "stt_device": "cpu",
        "stt_whisperlive_host": "127.0.0.1:8000",
        "stt_whisperlive_model": "small",
        "stt_external_api": False,
        "stt_host": "api.openai.com",
        "stt_remote_model": "whisper-1",
        "stt_vosk_model_path": "",
        "llm_backend": "profile",
        "llm_profile": "koboldcpp",
        "llm_device": "cpu",
        "llm_external_api": False,
        "llm_host": "api.openai.com",
        "llm_model": "gpt-4.1-mini",
        "tts_profile": "kokorotts",
        "tts_device": "cpu",
        "tts_external_api": False,
        "barge_in_enabled": True,
        "barge_in_threshold": "0.035",
        "stt_streaming_enabled": False,
        "llm_streaming_enabled": True,
        "tts_streaming_enabled": True,
        "tts_streaming_min_chars": "42",
        "tts_streaming_max_chars": "180",
        "emotion_tags_enabled": True,
        "token_saver_enabled": True,
        "privacy_word_coding_enabled": False,
        "privacy_words": "",
        "memory_enabled": False,
        "memory_host": "127.0.0.1:1234",
        "memory_model": "nomic-embed-text-v2-moe",
        "memory_top_k": "4",
        "memory_max_chars": "1100",
        "enable_character": True,
        "hide_character_photo": False,
        "hide_answer_text": False,
        "generic_notification_text": "Notification received",
        "stop_phrases_enabled": True,
        "stop_phrases_language": "en-us",
        "stop_phrases_allow_single_word": False,
    }


def _voice_recording_rms(audio_path: Path) -> float:
    try:
        import audioop
        with wave.open(str(audio_path), "rb") as w:
            width = w.getsampwidth()
            frames = w.readframes(w.getnframes())
        if not frames:
            return 0.0
        peak = float((1 << (8 * width - 1)) - 1)
        return audioop.rms(frames, width) / peak if peak > 0 else 0.0
    except Exception:
        return 0.0


def _wav_duration_seconds(audio_path: Path) -> float:
    try:
        with wave.open(str(audio_path), "rb") as w:
            return w.getnframes() / w.getframerate()
    except Exception:
        return 0.0


_STOP_CACHE = {"loaded": False, "data": {}}


def _load_voice_stop_expressions() -> dict:
    if _STOP_CACHE["loaded"]:
        return _STOP_CACHE["data"]
    data: dict = {}
    try:
        if VOICE_STOP_EXPRESSIONS_FILE.exists():
            raw = json.loads(VOICE_STOP_EXPRESSIONS_FILE.read_text(encoding="utf-8"))
            for lang, phrases in raw.items():
                if isinstance(phrases, list):
                    data[lang.strip().lower()] = [str(p).strip() for p in phrases if str(p).strip()]
    except Exception:
        pass
    _STOP_CACHE["loaded"] = True
    _STOP_CACHE["data"] = data
    return data


def _normalize_stop_text(text: str) -> str:
    import unicodedata
    clean = text.strip().lower()
    try:
        clean = "".join(c for c in unicodedata.normalize("NFKD", clean) if not unicodedata.combining(c))
    except Exception:
        pass
    return re.sub(r"[^a-z0-9\s]+", " ", clean).strip()


def _matches_stop_phrase(text: str, config: dict) -> bool:
    if not config.get("stop_phrases_enabled", True):
        return False
    lang = config.get("stop_phrases_language", "en-us").strip().lower() or "en-us"
    allow_single = config.get("stop_phrases_allow_single_word", False)
    phrases = _load_voice_stop_expressions().get(lang) or _load_voice_stop_expressions().get("en-us", [])
    if not phrases:
        return False
    norm = _normalize_stop_text(text)
    if not norm:
        return False
    for p in phrases:
        p_norm = _normalize_stop_text(p)
        if not p_norm:
            continue
        if not allow_single and " " not in p_norm and len(p_norm) <= 5:
            continue
        if norm == p_norm or norm.startswith(p_norm + " "):
            return True
    return False


import json


def _record_microphone_wav(seconds: float) -> Path:
    VOICE_RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    duration = max(0.25, min(30.0, float(seconds or 5.0)))
    output = VOICE_RECORDINGS_DIR / f"voice_{int(time.time() * 1000)}.wav"
    commands = []
    if shutil.which("ffmpeg"):
        commands.append(["ffmpeg", "-y", "-f", "pulse", "-i", "default", "-t", f"{duration:.2f}", "-ac", "1", "-ar", "16000", str(output)])
    if shutil.which("arecord"):
        commands.append(["arecord", "-q", "-f", "S16_LE", "-c", "1", "-r", "16000", "-d", str(max(1, int(duration))), str(output)])
    if shutil.which("pw-record"):
        commands.append(["pw-record", "--channels", "1", "--rate", "16000", str(output)])
    if not commands:
        raise RuntimeError("Install ffmpeg, arecord, or pw-record.")
    for cmd in commands:
        try:
            subprocess.run(cmd, capture_output=True, timeout=duration + 4, check=True)
            if output.exists() and output.stat().st_size > 44:
                return output
        except Exception:
            continue
    raise RuntimeError("Microphone recording failed.")


def _voice_venv_dir(engine: str, model: str, device: str) -> Path:
    return AI_STATE_DIR / "voice-venvs" / _safe_slug(engine) / _safe_slug(model) / _safe_slug(device)


def _voice_venv_python(engine: str, model: str, device: str) -> Path:
    return _voice_venv_dir(engine, model, device) / "bin" / "python3"


def _ensure_voice_venv(engine: str, model: str, device: str, requirements: list, import_name: str) -> Path:
    venv_dir = _voice_venv_dir(engine, model, device)
    python_bin = _voice_venv_python(engine, model, device)
    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    if not python_bin.exists():
        result = subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], capture_output=True, timeout=120)
        if result.returncode != 0 or not python_bin.exists():
            raise RuntimeError("Failed to create voice venv.")
    check = subprocess.run([str(python_bin), "-c", f"import {import_name}"], capture_output=True, timeout=30)
    if check.returncode == 0:
        return python_bin
    subprocess.run([str(python_bin), "-m", "pip", "install", "-U", "pip", "setuptools", "wheel"], capture_output=True, timeout=240)
    result = subprocess.run([str(python_bin), "-m", "pip", "install", *requirements], capture_output=True, timeout=900)
    if result.returncode != 0:
        raise RuntimeError("Voice runtime install failed.")
    return python_bin


def _privacy_word_list(config: dict) -> list:
    words = [w.strip() for w in config.get("privacy_words", "").replace(",", "\n").splitlines() if w.strip()]
    seen = set()
    deduped = []
    for w in words:
        if w.lower() not in seen:
            seen.add(w.lower())
            deduped.append(w)
    return deduped


def _write_privacy_codebook(config: dict) -> str:
    if not config.get("privacy_word_coding_enabled", False):
        if VOICE_PRIVACY_CODEBOOK_FILE.exists():
            VOICE_PRIVACY_CODEBOOK_FILE.unlink(missing_ok=True)
        return ""
    words = _privacy_word_list(config)
    if not words:
        return ""
    AI_STATE_DIR.mkdir(parents=True, exist_ok=True)
    lines = ["# Hanauta AI voice privacy codebook", ""]
    for i, w in enumerate(words, 1):
        lines.append(f"__HX_{i:03d}__ = {w}")
    VOICE_PRIVACY_CODEBOOK_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        import os as _os
        _os.chmod(VOICE_PRIVACY_CODEBOOK_FILE, 0o600)
    except Exception:
        pass
    return str(VOICE_PRIVACY_CODEBOOK_FILE)


VOICE_EMOTIONS = {
    "neutral", "happy", "sad", "angry", "excited", "shy", "playful",
    "calm", "flirty", "serious", "embarrassed", "teasing", "affectionate",
}


def _replace_sensitive_words(text: str, words: list) -> tuple:
    masked = str(text)
    mapping: dict = {}
    for index, word in enumerate(words, start=1):
        clean = word.strip()
        if not clean:
            continue
        token = f"__HX_{index:03d}__"
        mapping[token] = clean
        masked = re.sub(re.escape(clean), token, masked, flags=re.IGNORECASE)
    return masked, mapping


def _restore_sensitive_words(text: str, mapping: dict) -> str:
    restored = str(text)
    for token, value in mapping.items():
        restored = restored.replace(token, value)
    return restored


def _emotion_prompt_suffix(enabled: bool) -> str:
    if not enabled:
        return ""
    return (
        "Before each assistant reply, add exactly one leading emotion tag like "
        "[neutral], [happy], [sad], [angry], [excited], [shy], [playful], [calm], "
        "[flirty], [serious], [embarrassed], [teasing], or [affectionate]. "
        "Use one tag only, then continue with the reply text."
    )


def _extract_emotion_and_clean_text(text: str) -> tuple:
    clean = text.strip()
    match = re.match(r"^\s*\[([a-zA-Z_ -]{2,24})\]\s*", clean)
    if not match:
        return "neutral", clean
    emotion = match.group(1).strip().lower().replace(" ", "_")
    emotion = emotion if emotion in VOICE_EMOTIONS else "neutral"
    return emotion, clean[match.end():].strip()


__all__ = [
    "_voice_mode_defaults",
    "_voice_recording_rms",
    "_wav_duration_seconds",
    "_load_voice_stop_expressions",
    "_normalize_stop_text",
    "_matches_stop_phrase",
    "_record_microphone_wav",
    "_voice_venv_dir",
    "_voice_venv_python",
    "_ensure_voice_venv",
    "_privacy_word_list",
    "_write_privacy_codebook",
    "VOICE_EMOTIONS",
    "_replace_sensitive_words",
    "_restore_sensitive_words",
    "_emotion_prompt_suffix",
    "_extract_emotion_and_clean_text",
]
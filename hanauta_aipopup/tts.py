from __future__ import annotations

import hashlib
import importlib
import json
import os
import shlex
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import wave
import zipfile
from base64 import b64decode
from pathlib import Path
from urllib import error, request
from urllib.parse import urlparse

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt

from .models import BackendProfile, CharacterCard, ChatItemData, SourceChipData
from .runtime import (
    AI_STATE_DIR,
    BACKEND_ICONS_DIR,
    CHAT_ARCHIVES_DIR,
    GGUF_GALLERY_DIR,
    IMAGE_OUTPUT_DIR,
    KOBOLDCPP_RELEASE_STATE_FILE,
    KOKORO_SYNTH_LOG_FILE,
    KOKORO_ONNX_REPO,
    KOKORO_TTS_RELEASE_URL,
    MODEL_CATALOG_FILE,
    POCKET_ONNX_REPO,
    POCKETTTS_LANGUAGE_CODES,
    POCKETTTS_LANGUAGES,
    POCKETTTS_PRESET_VOICES,
    POCKETTTS_REFERENCE_DIR,
    POCKETTTS_SERVER_BINARY_NAME,
    POCKETTTS_SERVER_INFER_SCRIPT_NAME,
    POCKETTTS_SERVER_INSTALL_DIR,
    POCKETTTS_SERVER_SRC_DIR,
    POCKETTTS_VOICES_REPO,
    TTS_MODELS_DIR,
    TTS_OUTPUT_DIR,
    VOICE_MEMORY_DB_FILE,
    VOICE_TOKEN_COMPRESSOR_FILE,
    VOICE_TOKEN_COMPRESSOR_SAMPLE_FILE,
    trigger_fullscreen_alert,
)
from .style import ACCENT, ACCENT_SOFT, BORDER_ACCENT, CARD_BG, BORDER_SOFT, TEXT, TEXT_DIM, TEXT_MID, THEME, mix, rgba
from .storage import secure_load_secret
from .http import (
    _normalize_host_url,
    _http_json,
    _http_post_bytes,
    _http_post_json,
    _http_post_multipart,
    _sd_auth_headers,
    _sdapi_not_found_message,
    _hf_resolve_url,
    _download_file,
    _download_hf_files,
    _download_and_extract_zip_bundle,
    _openai_compat_alive,
    send_desktop_notification,
)
from .backends import _existing_path, _is_pid_alive, _is_pgid_alive
from .catalog import _format_bytes
from .characters import _character_compose_prompt
from .storage import _chmod_private
from .prompt_smartness import PromptSmartness
from .voice import (
    _privacy_word_list,
    _replace_sensitive_words,
    _restore_sensitive_words,
    _extract_emotion_and_clean_text,
    _emotion_prompt_suffix,
    VOICE_EMOTIONS,
)

import logging
LOGGER = logging.getLogger("hanauta.ai_popup")

_KOKORO_RUNTIME_READY = False
_WAVEFORM_CACHE: dict[str, list[int]] = {}


def _ansi(text: str, code: str) -> str:
    import sys
    stream = getattr(sys, "stderr", None)
    if stream is not None and hasattr(stream, "isatty") and stream.isatty():
        return f"\033[{code}m{text}\033[0m"
    return text


def _voice_log(kind: str, backend: str, model: str, message: str) -> None:
    palette = {
        "stt": ("38;5;117", "38;5;153"),
        "llm": ("38;5;213", "38;5;219"),
    }
    backend_color, model_color = palette.get(kind, ("38;5;250", "38;5;255"))
    title = "Voice STT transcript" if kind == "stt" else "Voice LLM reply"
    pretty = (
        f"{_ansi(title, '1;97')} "
        f"({_ansi('backend', '38;5;245')}: {_ansi(backend, backend_color)}, "
        f"{_ansi('model', '38;5;245')}: {_ansi(model, model_color)}): "
        f"{message}"
    )
    LOGGER.info(pretty)


def _render_llm_text_html(text: str) -> str:
    return _PROMPT_SMARTNESS.render_llm_text_html(text)


def _strip_simple_markdown(text: str) -> str:
    return _PROMPT_SMARTNESS.strip_simple_markdown(text)

def _safe_slug(value: str) -> str:
    raw = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.strip())
    compact = "_".join(part for part in raw.split("_") if part)
    return compact[:80] if compact else "audio"


def _write_wav_from_float32_mono(path: Path, samples: "np.ndarray", sample_rate: int = 24000) -> None:
    import numpy as np

    clipped = np.clip(samples.astype(np.float32), -1.0, 1.0)
    int16 = (clipped * 32767.0).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(int(sample_rate))
        wav.writeframes(int16.tobytes())


def _play_audio_file(audio_path: Path) -> None:
    commands = [
        ["pw-play", str(audio_path)],
        ["aplay", str(audio_path)],
        ["ffplay", "-autoexit", "-nodisp", "-loglevel", "quiet", str(audio_path)],
    ]
    for command in commands:
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            if process.pid:
                return
        except Exception:
            continue


def _voice_mode_defaults() -> dict[str, object]:
    return {
        "enabled": False,
        "record_seconds": "5",
        "silence_threshold": "0.012",
        # End-of-speech detector tuning (record-until-silence):
        # - adaptive gate uses an estimated noise floor to reduce premature cut-offs on noisy mics
        # - hysteresis counts "silence" only when RMS drops below threshold * hysteresis
        "eos_adaptive_enabled": True,
        "eos_noise_margin": "0.004",
        "eos_hysteresis": "0.82",
        # End-of-speech detection: after speech begins, stop recording once we've observed this
        # much trailing silence (ms). Set to 0 to use fixed-length recording windows only.
        "speech_end_silence_ms": "750",
        # Microphone chunk size (seconds) while listening for end-of-speech. Smaller feels snappier but
        # can cost CPU and increase the chance of gaps between chunks depending on the recorder.
        "listen_chunk_seconds": "0.75",
        # Minimum speech time (ms) required before we allow trailing-silence stop.
        "min_speech_ms": "260",
        "stt_backend": "whisper",
        "stt_model": "small",
        "stt_device": "cpu",
        # Optional WhisperLive server (collabora/WhisperLive) using its OpenAI REST interface.
        "stt_whisperlive_host": "127.0.0.1:9090",
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
        # Streaming mode (more realistic voice agents): show live transcript, stream LLM tokens, and
        # speak the reply as it is generated (best with PocketTTS + KoboldCpp streaming).
        "stt_streaming_enabled": False,
        "llm_streaming_enabled": True,
        "tts_streaming_enabled": True,
        "tts_streaming_min_chars": "42",
        "tts_streaming_max_chars": "180",
        "emotion_tags_enabled": True,
        # Token saver: compress voice transcripts before sending to LLM (reduces tokens).
        "token_saver_enabled": True,
        "privacy_word_coding_enabled": False,
        "privacy_words": "",
        # Embedding memory: optional retrieval snippets injected into the prompt.
        "memory_enabled": False,
        "memory_host": "127.0.0.1:1234",
        "memory_model": "nomic-embed-text-v2-moe",
        "memory_top_k": "4",
        "memory_max_chars": "1100",
        "compaction_model_host": "",
        "compaction_model_name": "",
        "enable_character": True,
        "hide_character_photo": False,
        "hide_answer_text": False,
        "generic_notification_text": "Notification received",
        # Stop expressions: optional voice command detection to stop the hands-free loop.
        "stop_phrases_enabled": True,
        "stop_phrases_language": "en-us",
        "stop_phrases_allow_single_word": False,
    }


def _voice_mode_settings(settings: dict[str, dict[str, object]]) -> dict[str, object]:
    payload = dict(_voice_mode_defaults())
    raw = settings.get("_voice_mode", {})
    if isinstance(raw, dict):
        payload.update(raw)
    # Auto-switch STT to "LLM audio" when KoboldCpp is running Gemma 4 audio variants and the user opted in.
    # This avoids loading Whisper entirely (lower VRAM), and uses the same LLM for STT+chat.
    try:
        if (
            not bool(payload.get("stt_external_api", False))
            and not bool(payload.get("llm_external_api", False))
            and str(payload.get("stt_backend", "whisper")).strip().lower() == "whisper"
            and str(payload.get("llm_profile", "koboldcpp")).strip() == "koboldcpp"
        ):
            kobold = dict(settings.get("koboldcpp", {}) or {})
            if bool(kobold.get("gemma4_audio_stt_enabled", False)) and bool(kobold.get("gemma4_audio_supported", False)):
                gguf = str(kobold.get("gguf_path", "")).strip()
                gguf_name = Path(gguf).name if gguf else ""
                checked_gguf = str(kobold.get("gemma4_audio_checked_gguf", "")).strip()
                if checked_gguf and checked_gguf != gguf_name:
                    pass
                elif _looks_like_gemma4_model_name(gguf_name):
                    payload["stt_backend"] = "llm_audio"
    except Exception:
        pass
    return payload


def _with_voice_device(payload: dict[str, object], device: str) -> dict[str, object]:
    updated = dict(payload)
    clean = device.strip().lower()
    if clean in {"cpu", "gpu"}:
        updated["device"] = clean
    return updated


def _api_url_from_host(host: str) -> str:
    clean = host.strip().rstrip("/")
    if not clean:
        return ""
    if clean.startswith(("http://", "https://")):
        return clean
    if clean in {"api.openai.com", "www.api.openai.com"} or clean.endswith(".openai.com"):
        return f"https://{clean}"
    return f"http://{clean}"


_PROMPT_SMARTNESS = PromptSmartness(
    state_dir=AI_STATE_DIR,
    token_compressor_sample_file=VOICE_TOKEN_COMPRESSOR_SAMPLE_FILE,
    token_compressor_file=VOICE_TOKEN_COMPRESSOR_FILE,
    memory_db_file=VOICE_MEMORY_DB_FILE,
    http_post_json=_http_post_json,
    api_url_from_host=_api_url_from_host,
    load_secret=secure_load_secret,
    chmod_private=_chmod_private,
)


def _voice_recording_rms(audio_path: Path) -> float:
    try:
        import audioop

        with wave.open(str(audio_path), "rb") as handle:
            width = int(handle.getsampwidth() or 2)
            frames = handle.readframes(int(handle.getnframes() or 0))
        if not frames:
            return 0.0
        peak = float((1 << (8 * width - 1)) - 1)
        return float(audioop.rms(frames, width)) / peak if peak > 0 else 0.0
    except Exception:
        return 0.0


def _wav_duration_seconds(audio_path: Path) -> float:
    try:
        with wave.open(str(audio_path), "rb") as handle:
            frames = int(handle.getnframes() or 0)
            rate = int(handle.getframerate() or 0)
        return (frames / float(rate)) if rate > 0 else 0.0
    except Exception:
        return 0.0


_VOICE_STOP_CACHE: dict[str, object] = {"loaded": False, "payload": {}}


def _load_voice_stop_expressions() -> dict[str, list[str]]:
    if bool(_VOICE_STOP_CACHE.get("loaded", False)):
        payload = _VOICE_STOP_CACHE.get("payload", {})
        return payload if isinstance(payload, dict) else {}
    payload: dict[str, list[str]] = {}
    try:
        if VOICE_STOP_EXPRESSIONS_FILE.exists():
            raw = json.loads(VOICE_STOP_EXPRESSIONS_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for lang, phrases in raw.items():
                    if isinstance(lang, str) and isinstance(phrases, list):
                        clean = [str(p).strip() for p in phrases if str(p).strip()]
                        if clean:
                            payload[lang.strip().lower()] = clean
    except Exception:
        payload = {}
    _VOICE_STOP_CACHE["loaded"] = True
    _VOICE_STOP_CACHE["payload"] = payload
    return payload


def _normalize_stop_text(text: str) -> str:
    clean = str(text or "").strip().lower()
    if not clean:
        return ""
    try:
        import unicodedata

        clean = "".join(
            ch for ch in unicodedata.normalize("NFKD", clean)
            if not unicodedata.combining(ch)
        )
    except Exception:
        pass
    # Keep letters/numbers/spaces only
    clean = re.sub(r"[^a-z0-9\s]+", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _matches_stop_phrase(text: str, config: dict[str, object]) -> bool:
    if not bool(config.get("stop_phrases_enabled", True)):
        return False
    lang = str(config.get("stop_phrases_language", "en-us")).strip().lower() or "en-us"
    allow_single = bool(config.get("stop_phrases_allow_single_word", False))
    payload = _load_voice_stop_expressions()
    phrases = list(payload.get(lang, []))
    # Fallback to English if requested language missing.
    if not phrases and lang != "en-us":
        phrases = list(payload.get("en-us", []))
    if not phrases:
        return False
    norm = _normalize_stop_text(text)
    if not norm:
        return False
    for phrase in phrases:
        p = _normalize_stop_text(phrase)
        if not p:
            continue
        # By default, only accept multi-word (or explicit) phrases to avoid false positives.
        if (not allow_single) and (" " not in p) and (len(p) <= 5):
            continue
        if norm == p:
            return True
        if norm.startswith(p + " "):
            return True
    return False


def _record_microphone_wav(seconds: float) -> Path:
    VOICE_RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    duration = max(0.25, min(30.0, float(seconds or 5.0)))
    output = VOICE_RECORDINGS_DIR / f"voice_{int(time.time() * 1000)}.wav"
    commands: list[list[str]] = []
    if shutil.which("ffmpeg"):
        commands.append([
            "ffmpeg",
            "-y",
            "-f",
            "pulse",
            "-i",
            "default",
            "-t",
            f"{duration:.2f}",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(output),
        ])
    if shutil.which("arecord"):
        commands.append([
            "arecord",
            "-q",
            "-f",
            "S16_LE",
            "-c",
            "1",
            "-r",
            "16000",
            "-d",
            str(max(1, int(round(duration)))),
            str(output),
        ])
    if shutil.which("pw-record"):
        commands.append([
            "pw-record",
            "--channels",
            "1",
            "--rate",
            "16000",
            str(output),
        ])
    if not commands:
        raise RuntimeError("Install ffmpeg, arecord, or pw-record to capture microphone audio.")
    last_error = ""
    for command in commands:
        try:
            timeout = duration + 4.0
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if result.returncode == 0 and output.exists() and output.stat().st_size > 44:
                return output
            last_error = (result.stderr or result.stdout or "").strip()
        except subprocess.TimeoutExpired:
            if output.exists() and output.stat().st_size > 44:
                return output
            last_error = "microphone recorder timed out"
        except Exception as exc:
            last_error = str(exc)
    raise RuntimeError(last_error or "Microphone recording failed.")


def _transcribe_with_external_api(audio_path: Path, config: dict[str, object]) -> str:
    host = str(config.get("stt_host", "")).strip()
    if not host:
        raise RuntimeError("External STT requires a host.")
    api_key = secure_load_secret("voice_mode:stt_api_key").strip()
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    fields = {
        "model": str(config.get("stt_remote_model", "whisper-1")).strip() or "whisper-1",
        "response_format": "json",
    }
    payload = _http_post_multipart(
        f"{_api_url_from_host(host)}/v1/audio/transcriptions",
        fields=fields,
        files={"file": (audio_path.name, audio_path.read_bytes(), "audio/wav")},
        headers=headers,
        timeout=240.0,
    )
    text = str(payload.get("text", "")).strip()
    if not text:
        raise RuntimeError("STT endpoint returned no text.")
    return text


def _transcribe_with_whisperlive(audio_path: Path, config: dict[str, object], *, prompt: str = "") -> str:
    """
    WhisperLive (collabora/WhisperLive) can expose an OpenAI-compatible REST endpoint when launched
    with --enable_rest. We talk to it as a local STT provider.
    """
    logging.info("[WhisperLive] transcribe: audio=%s prompt=%s", audio_path.name, prompt[:30] if prompt else "")
    host = str(config.get("stt_whisperlive_host", "")).strip()
    if not host:
        raise RuntimeError("WhisperLive STT requires a host.")
    api_url = _api_url_from_host(host)
    logging.info("[WhisperLive] health check: %s", api_url)
    if not _host_reachable(api_url, timeout=3.0):
        raise RuntimeError(f"WhisperLive is not ready at {api_url}")
    try:
        with request.urlopen(f"{api_url}/v1/models", timeout=3.0) as resp:
            if resp.status >= 400:
                raise RuntimeError(f"WhisperLive returned status {resp.status}")
            logging.info("[WhisperLive] health: /v1/models status=%d", resp.status)
    except Exception as exc:
        raise RuntimeError(f"WhisperLive health check failed: {exc}")
    model = str(config.get("stt_whisperlive_model", "small")).strip() or "small"
    fields: dict[str, str] = {"model": model, "response_format": "json"}
    if prompt.strip():
        fields["prompt"] = prompt.strip()
    logging.info("[WhisperLive] posting to %s/model=%s", host, model)
    payload = _http_post_multipart(
        f"{_api_url_from_host(host)}/v1/audio/transcriptions",
        fields=fields,
        files={"file": (audio_path.name, audio_path.read_bytes(), "audio/wav")},
        headers={},
        timeout=240.0,
    )
    text = str(payload.get("text", "")).strip()
    logging.info("[WhisperLive] result: %s", text[:50] if text else "(empty)")
    if not text:
        raise RuntimeError("WhisperLive STT returned no text.")
    return text


def _voice_venv_dir(engine: str, model_name: str, device: str) -> Path:
    engine_slug = _safe_slug(engine.strip().lower() or "voice")
    model_slug = _safe_slug(model_name.strip().lower() or "model")
    device_slug = _safe_slug(device.strip().lower() or "cpu")
    return AI_STATE_DIR / "voice-venvs" / engine_slug / model_slug / device_slug


def _voice_venv_python(engine: str, model_name: str, device: str) -> Path:
    return _voice_venv_dir(engine, model_name, device) / "bin" / "python3"


def _ensure_voice_venv(
    engine: str,
    model_name: str,
    device: str,
    requirements: list[str],
    import_name: str,
) -> Path:
    venv_dir = _voice_venv_dir(engine, model_name, device)
    python_bin = _voice_venv_python(engine, model_name, device)
    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    if not python_bin.exists():
        result = subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        if result.returncode != 0 or not python_bin.exists():
            detail = (result.stderr or result.stdout or "").strip().splitlines()[-10:]
            raise RuntimeError("Failed to create voice model virtualenv:\n" + "\n".join(detail).strip())
    import_check = subprocess.run(
        [str(python_bin), "-c", f"import {import_name}"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if import_check.returncode == 0:
        return python_bin
    subprocess.run(
        [str(python_bin), "-m", "pip", "install", "-U", "pip", "setuptools", "wheel"],
        capture_output=True,
        text=True,
        check=False,
        timeout=240,
    )
    result = subprocess.run(
        [str(python_bin), "-m", "pip", "install", *requirements],
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()[-14:]
        raise RuntimeError(
            "Voice STT runtime install failed in the isolated venv:\n"
            + "\n".join(detail).strip()
        )
    return python_bin


def _voice_whisper_script_path() -> Path:
    return AI_STATE_DIR / "voice-runtime" / "faster_whisper_transcribe.py"


def _ensure_voice_whisper_script() -> Path:
    script_path = _voice_whisper_script_path()
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_text = """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from faster_whisper import WhisperModel
from huggingface_hub import snapshot_download


MODEL_REPOS = {
    "tiny": "Systran/faster-whisper-tiny",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large": "Systran/faster-whisper-large-v3",
}


def _resolve_model_path(model_name: str, model_cache: Path) -> Path:
    if model_name.startswith("/") or model_name.startswith("."):
        candidate = Path(model_name).expanduser()
        if candidate.exists():
            return candidate
    repo_id = MODEL_REPOS.get(model_name, model_name)
    target = model_cache / repo_id.replace("/", "--")
    if target.exists():
        return target
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "35")
    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "20")
    try:
        snapshot_download(
            repo_id=repo_id,
            local_dir=str(target),
            local_dir_use_symlinks=False,
            max_workers=4,
            etag_timeout=20,
        )
    except KeyboardInterrupt:
        raise RuntimeError(
            "Whisper model download was interrupted. "
            "Please wait for the first model download to finish, or switch STT to External API."
        )
    except Exception as exc:
        raise RuntimeError(
            f"Unable to download the Whisper model '{model_name}' into {target}: {exc}"
        ) from exc
    return target


def _try_transcribe(model_name: str, audio_path: Path, device: str, compute_type: str, model_cache: Path) -> str:
    resolved_model = _resolve_model_path(model_name, model_cache)
    model = WhisperModel(
        str(resolved_model),
        device=device,
        compute_type=compute_type,
    )
    segments, _info = model.transcribe(str(audio_path), vad_filter=True, beam_size=1)
    return " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--audio", required=True)
    parser.add_argument("--device", choices=["cpu", "gpu"], default="cpu")
    parser.add_argument("--model-cache", required=True)
    args = parser.parse_args()
    audio_path = Path(args.audio).expanduser()
    model_cache = Path(args.model_cache).expanduser()
    model_cache.mkdir(parents=True, exist_ok=True)
    attempts = []
    if args.device == "gpu":
        attempts.extend([
            ("cuda", "float16"),
            ("cuda", "int8_float16"),
        ])
    attempts.extend([
        ("cpu", "int8"),
        ("cpu", "int8_float32"),
    ])
    errors = []
    for device, compute_type in attempts:
        try:
            text = _try_transcribe(args.model, audio_path, device, compute_type, model_cache)
            print(json.dumps({"text": text, "device": device, "compute_type": compute_type}))
            return 0
        except Exception as exc:
            errors.append(f"{device}/{compute_type}: {exc}")
    print(json.dumps({"error": "\\n".join(errors[-4:])}), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
"""
    script_path.write_text(script_text, encoding="utf-8")
    try:
        os.chmod(script_path, 0o700)
    except Exception:
        pass
    return script_path


def _voice_whisper_stream_script_path() -> Path:
    return AI_STATE_DIR / "voice-runtime" / "faster_whisper_stream.py"


def _ensure_voice_whisper_stream_script() -> Path:
    script_path = _voice_whisper_stream_script_path()
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_text = """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
from pathlib import Path

from faster_whisper import WhisperModel
from huggingface_hub import snapshot_download


MODEL_REPOS = {
    "tiny": "Systran/faster-whisper-tiny",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large": "Systran/faster-whisper-large-v3",
}


def _resolve_model_path(model_name: str, model_cache: Path) -> Path:
    if model_name.startswith("/") or model_name.startswith("."):
        candidate = Path(model_name).expanduser()
        if candidate.exists():
            return candidate
    repo_id = MODEL_REPOS.get(model_name, model_name)
    target = model_cache / repo_id.replace("/", "--")
    if target.exists():
        return target
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "35")
    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "20")
    snapshot_download(
        repo_id=repo_id,
        local_dir=str(target),
        local_dir_use_symlinks=False,
        max_workers=4,
        etag_timeout=20,
    )
    return target


def _transcribe(model: WhisperModel, audio_path: Path, prompt: str) -> str:
    kwargs = {"beam_size": 1}
    # Optional params across faster-whisper versions.
    try:
        sig = inspect.signature(model.transcribe)
        params = set(sig.parameters.keys())
        if "vad_filter" in params:
            kwargs["vad_filter"] = True
        if prompt and "initial_prompt" in params:
            kwargs["initial_prompt"] = prompt
        if "condition_on_previous_text" in params:
            kwargs["condition_on_previous_text"] = True
    except Exception:
        kwargs["vad_filter"] = True
    segments, _info = model.transcribe(str(audio_path), **kwargs)
    return " ".join(seg.text.strip() for seg in segments if seg.text.strip()).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--device", choices=["cpu", "gpu"], default="cpu")
    parser.add_argument("--model-cache", required=True)
    args = parser.parse_args()

    model_cache = Path(args.model_cache).expanduser()
    model_cache.mkdir(parents=True, exist_ok=True)

    attempts = []
    if args.device == "gpu":
        attempts.extend([("cuda", "float16"), ("cuda", "int8_float16")])
    attempts.extend([("cpu", "int8"), ("cpu", "int8_float32")])

    resolved_model = _resolve_model_path(args.model, model_cache)
    loaded = None
    last_error = ""
    for device, compute_type in attempts:
        try:
            loaded = WhisperModel(str(resolved_model), device=device, compute_type=compute_type)
            print(json.dumps({"ready": True, "device": device, "compute_type": compute_type}), flush=True)
            break
        except Exception as exc:
            last_error = str(exc)
            continue
    if loaded is None:
        print(json.dumps({"ready": False, "error": last_error}), flush=True)
        return 2

    for line in sys.stdin:
        raw = line.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except Exception:
            continue
        if not isinstance(msg, dict):
            continue
        cmd = str(msg.get("cmd", "")).strip()
        if cmd == "shutdown":
            print(json.dumps({"ok": True}), flush=True)
            return 0
        if cmd != "transcribe":
            continue
        audio = Path(str(msg.get("audio", "")).strip()).expanduser()
        prompt = str(msg.get("prompt", "")).strip()
        if not audio.exists():
            print(json.dumps({"ok": False, "error": "audio not found"}), flush=True)
            continue
        try:
            text = _transcribe(loaded, audio, prompt)
            print(json.dumps({"ok": True, "text": text}), flush=True)
        except Exception as exc:
            print(json.dumps({"ok": False, "error": str(exc)}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""
    script_path.write_text(script_text, encoding="utf-8")
    try:
        os.chmod(script_path, 0o700)
    except Exception:
        pass
    return script_path


def _voice_vosk_script_path() -> Path:
    return AI_STATE_DIR / "voice-runtime" / "vosk_transcribe.py"


def _ensure_voice_vosk_script() -> Path:
    script_path = _voice_vosk_script_path()
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_text = """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import wave

import vosk


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--audio", required=True)
    args = parser.parse_args()
    model_path = Path(args.model_path).expanduser()
    audio_path = Path(args.audio).expanduser()
    chunks = []
    with wave.open(str(audio_path), "rb") as handle:
        if handle.getnchannels() != 1 or handle.getframerate() not in {8000, 16000, 24000, 48000}:
            raise RuntimeError("VOSK needs mono WAV audio.")
        recognizer = vosk.KaldiRecognizer(vosk.Model(str(model_path)), handle.getframerate())
        while True:
            data = handle.readframes(4000)
            if not data:
                break
            if recognizer.AcceptWaveform(data):
                parsed = json.loads(recognizer.Result())
                text = str(parsed.get("text", "")).strip()
                if text:
                    chunks.append(text)
        parsed = json.loads(recognizer.FinalResult())
        final = str(parsed.get("text", "")).strip()
        if final:
            chunks.append(final)
    print(json.dumps({"text": " ".join(chunks).strip()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""
    script_path.write_text(script_text, encoding="utf-8")
    try:
        os.chmod(script_path, 0o700)
    except Exception:
        pass
    return script_path


def _transcribe_with_whisper(audio_path: Path, config: dict[str, object]) -> str:
    raw_model = str(config.get("stt_model", "small")).strip()
    lowered = raw_model.lower()
    # Allow Hugging Face repo IDs or local paths in addition to built-in size aliases.
    model_name = lowered if lowered in {"tiny", "small", "medium", "large"} else (raw_model or "small")
    device = "gpu" if str(config.get("stt_device", "cpu")).lower() == "gpu" else "cpu"
    python_bin = _ensure_voice_venv("whisper", model_name, device, ["faster-whisper", "huggingface-hub"], "faster_whisper")
    script_path = _ensure_voice_whisper_script()
    model_cache = _voice_venv_dir("whisper", model_name, device) / "model-cache"
    result = subprocess.run(
        [
            str(python_bin),
            str(script_path),
            "--model",
            model_name,
            "--audio",
            str(audio_path.expanduser()),
            "--device",
            device,
            "--model-cache",
            str(model_cache),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=1800,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()[-12:]
        raise RuntimeError(
            "Whisper STT failed in its isolated faster-whisper venv:\n"
            + "\n".join(detail).strip()
        )
    try:
        payload = json.loads((result.stdout or "").strip().splitlines()[-1])
    except Exception as exc:
        raise RuntimeError("Whisper STT returned invalid output.") from exc
    text = str(payload.get("text", "")).strip()
    if not text:
        raise RuntimeError("Whisper STT returned no text.")
    LOGGER.debug(
        "voice whisper transcribed with model=%s requested_device=%s actual_device=%s compute=%s",
        model_name,
        device,
        payload.get("device", ""),
        payload.get("compute_type", ""),
    )
    return text



def _transcribe_with_vosk(audio_path: Path, config: dict[str, object]) -> str:
    model_path = Path(str(config.get("stt_vosk_model_path", "")).strip()).expanduser()
    if not str(model_path).strip() or not model_path.exists():
        raise RuntimeError("Set a local VOSK English model folder in Voice Mode settings.")
    model_key = hashlib.sha1(str(model_path.resolve()).encode("utf-8", "ignore")).hexdigest()[:12]
    python_bin = _ensure_voice_venv("vosk", model_key, "cpu", ["vosk"], "vosk")
    script_path = _ensure_voice_vosk_script()
    result = subprocess.run(
        [
            str(python_bin),
            str(script_path),
            "--model-path",
            str(model_path),
            "--audio",
            str(audio_path.expanduser()),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()[-12:]
        raise RuntimeError(
            "VOSK STT failed in its isolated venv:\n"
            + "\n".join(detail).strip()
        )
    try:
        payload = json.loads((result.stdout or "").strip().splitlines()[-1])
    except Exception as exc:
        raise RuntimeError("VOSK STT returned invalid output.") from exc
    text = str(payload.get("text", "")).strip()
    if not text:
        raise RuntimeError("VOSK STT returned no text.")
    return text


def _resolve_voice_llm_endpoint(
    config: dict[str, object],
    profiles: dict[str, BackendProfile] | None,
    backend_settings: dict[str, dict[str, object]] | None,
) -> tuple[str, str, str]:
    if bool(config.get("llm_external_api", False)):
        host = str(config.get("llm_host", "")).strip()
        model = str(config.get("llm_model", "")).strip() or "gpt-4.1-mini"
        api_key = secure_load_secret("voice_mode:llm_api_key").strip()
        return host, model, api_key
    if profiles is None or backend_settings is None:
        raise RuntimeError("LLM-audio STT needs the voice mode LLM backend settings.")
    profile_key = str(config.get("llm_profile", "koboldcpp")).strip()
    profile = profiles.get(profile_key)
    if profile is None:
        raise RuntimeError("Select an LLM backend in Voice Mode settings.")
    payload = dict(backend_settings.get(profile.key, {}))
    host = str(payload.get("host", profile.host)).strip()
    model = str(payload.get("model", profile.model)).strip() or profile.model
    api_key = secure_load_secret(f"{profile.key}:api_key").strip()
    return host, model, api_key


def _transcribe_with_llm_audio(
    audio_path: Path,
    config: dict[str, object],
    profiles: dict[str, BackendProfile] | None,
    backend_settings: dict[str, dict[str, object]] | None,
) -> str:
    host, model, api_key = _resolve_voice_llm_endpoint(config, profiles, backend_settings)
    if not host:
        raise RuntimeError("Set a voice mode LLM host before using LLM-audio STT.")
    audio_bytes = audio_path.expanduser().read_bytes()
    audio_b64 = b64encode(audio_bytes).decode("ascii")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    payload = {
        "model": model.strip() or "koboldcpp",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a speech-to-text transcriber. "
                    "Return only the spoken words as plain text. "
                    "No markdown, no extra commentary."
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_audio", "input_audio": {"data": audio_b64, "format": "wav"}},
                    {"type": "text", "text": "Transcribe the audio. Return only the transcription text."},
                ],
            },
        ],
        "temperature": 0,
        "max_tokens": 520,
    }
    response = _http_post_json(
        f"{_api_url_from_host(host)}/v1/chat/completions",
        payload,
        timeout=240.0,
        headers=headers,
    )
    choices = response.get("choices", [])
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message", {})
            if isinstance(message, dict):
                text = str(message.get("content", "")).strip()
                if text:
                    return text
            text = str(first.get("text", "")).strip()
            if text:
                return text
    raise RuntimeError("LLM-audio STT returned no transcript text.")


def transcribe_voice_audio(
    audio_path: Path,
    config: dict[str, object],
    profiles: dict[str, BackendProfile] | None = None,
    backend_settings: dict[str, dict[str, object]] | None = None,
) -> str:
    if bool(config.get("stt_external_api", False)):
        return _transcribe_with_external_api(audio_path, config)
    backend = str(config.get("stt_backend", "whisper")).strip().lower()
    if backend == "llm_audio":
        return _transcribe_with_llm_audio(audio_path, config, profiles, backend_settings)
    if backend == "vosk":
        return _transcribe_with_vosk(audio_path, config)
    if backend == "whisperlive":
        return _transcribe_with_whisperlive(audio_path, config)
    return _transcribe_with_whisper(audio_path, config)


def _resolve_character_template(text: str, char_name: str, user_name: str) -> str:
    """Replace {{char}} and {{user}} TavernAI template tokens."""
    return (
        text
        .replace("{{char}}", char_name)
        .replace("{{Char}}", char_name)
        .replace("{{user}}", user_name)
        .replace("{{User}}", user_name)
    )


def _tool_delivery_hint(char_name: str, user_name: str, has_notify: bool) -> str:
    """System instruction telling the character how to offer tool results to the user."""
    send_line = (
        f"If {user_name} would benefit from receiving the result on their phone or "
        f"another channel, {char_name} can offer to send it using the notify skill."
        if has_notify else ""
    )
    return (
        f"When {char_name} uses a tool and gets a result, {char_name} should offer "
        f"{user_name} two options: open the full log in a text viewer, or have "
        f"{char_name} summarise it conversationally. "
        + send_line
    ).strip()


def _chat_messages_for_prompt(
    prompt: str,
    character: CharacterCard | None,
    *,
    emotion_tags: bool = False,
    tools: list[dict] | None = None,
    user_name: str = "",
    user_info: str = "",
) -> list[dict[str, str]]:
    system = "You are Hanauta AI. Keep spoken replies concise, natural, and easy to listen to."
    # Inject user info if provided
    user_context = str(user_info or "").strip()
    if user_context:
        system = f"{system}\n\nUser info:\n{user_context}"
    if character is not None:
        char_name = character.name or "Assistant"
        resolved_user = user_name.strip() or "User"
        character_prompt = _resolve_character_template(
            _character_compose_prompt(character).strip(),
            char_name, resolved_user,
        )
        if character_prompt:
            system = f"{system}\n\nActive character:\n{character_prompt}"
        has_notify = bool(tools and any(
            (t.get("function", t).get("name", "") or "").startswith("notify_")
            for t in tools
        ))
        hint = _tool_delivery_hint(char_name, resolved_user, has_notify)
        if hint:
            system = f"{system}\n\n{hint}"
    # Inject live emotion context so the AI adapts its tone
    try:
        import importlib.util as _ilu
        from pathlib import Path as _P
        _ep = _P(__file__).parent.parent / "skills" / "py-emotion-engine.py"
        if _ep.exists():
            _spec = _ilu.spec_from_file_location("skills.emotion_engine", _ep)
            _em = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
            _spec.loader.exec_module(_em)  # type: ignore[union-attr]
            _ctx = _em.emotion_context_line()
            if _ctx:
                system = f"{system}\n\n{_ctx}"
    except Exception:
        pass
    if tools:
        system = f"{system}\n\n{_tools_system_prompt(tools)}"
    emotion_suffix = _emotion_prompt_suffix(emotion_tags)
    if emotion_suffix:
        system = f"{system}\n\n{emotion_suffix}"
    return [{"role": "system", "content": system}, {"role": "user", "content": prompt}]


def _chat_messages_with_memory(
    prompt: str,
    character: CharacterCard | None,
    *,
    emotion_tags: bool = False,
    memory: str = "",
    tools: list[dict] | None = None,
    user_name: str = "",
    user_info: str = "",
) -> list[dict[str, str]]:
    messages = _chat_messages_for_prompt(
        prompt, character,
        emotion_tags=emotion_tags, tools=tools, user_name=user_name,
        user_info=user_info,
    )
    memo = str(memory or "").strip()
    if not memo:
        return messages
    # Insert after the main system prompt.
    try:
        messages.insert(1, {"role": "system", "content": "Relevant memory (verbatim excerpts):\n" + memo})
    except Exception:
        pass
    return messages


def _voice_token_saver_enabled(
    config: dict[str, object],
    profiles: dict[str, BackendProfile],
    backend_settings: dict[str, dict[str, object]],
) -> bool:
    if not bool(config.get("token_saver_enabled", True)):
        return False
    if bool(config.get("llm_external_api", False)):
        return True
    profile_key = str(config.get("llm_profile", "koboldcpp")).strip()
    profile = profiles.get(profile_key)
    if profile is None:
        return True
    payload = dict(backend_settings.get(profile.key, {}))
    return bool(payload.get("token_saver_enabled", True))


def _load_voice_token_compressor() -> dict[str, object]:
    return _PROMPT_SMARTNESS.load_token_compressor()


def _compress_voice_prompt(text: str, config: dict[str, object]) -> str:
    del config
    return _PROMPT_SMARTNESS.compress_voice_prompt(text)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    return _PROMPT_SMARTNESS.cosine_similarity(a, b)


def _fetch_openai_style_embedding(host: str, model: str, text: str, api_key: str = "") -> list[float]:
    return _PROMPT_SMARTNESS.fetch_openai_style_embedding(host, model, text, api_key)


def _voice_memory_enabled(config: dict[str, object]) -> bool:
    return bool(config.get("memory_enabled", False)) and bool(str(config.get("memory_host", "")).strip())


def _voice_memory_db_init(conn: sqlite3.Connection) -> None:
    _PROMPT_SMARTNESS.memory_db_init(conn)


def _voice_memory_add(role: str, content: str, embedding: list[float]) -> None:
    _PROMPT_SMARTNESS.memory_add(role, content, embedding)


def _voice_memory_recall(config: dict[str, object], query: str) -> str:
    if not _voice_memory_enabled(config):
        return ""
    host = str(config.get("memory_host", "")).strip()
    model = str(config.get("memory_model", "")).strip() or "nomic-embed-text-v2-moe"
    api_key = secure_load_secret("voice_mode:memory_api_key").strip()
    try:
        top_k = int(str(config.get("memory_top_k", "4")).strip() or "4")
    except Exception:
        top_k = 4
    try:
        max_chars = int(str(config.get("memory_max_chars", "1100")).strip() or "1100")
    except Exception:
        max_chars = 1100
    return _PROMPT_SMARTNESS.memory_recall(host, model, api_key, query, top_k, max_chars)


def _voice_memory_store_pair(config: dict[str, object], user_text: str, assistant_text: str) -> None:
    if not _voice_memory_enabled(config):
        return
    host = str(config.get("memory_host", "")).strip()
    model = str(config.get("memory_model", "")).strip() or "nomic-embed-text-v2-moe"
    api_key = secure_load_secret("voice_mode:memory_api_key").strip()
    user_clean = str(user_text or "").strip()
    assistant_clean = str(assistant_text or "").strip()
    if not user_clean and not assistant_clean:
        return
    # Avoid persisting raw private words if the privacy feature is enabled.
    if bool(config.get("privacy_word_coding_enabled", False)):
        try:
            assistant_clean, _mapping = _replace_sensitive_words(assistant_clean, _privacy_word_list(config))
        except Exception:
            pass
    try:
        if user_clean:
            emb_u = _PROMPT_SMARTNESS.fetch_openai_style_embedding(host, model, user_clean, api_key)
            _PROMPT_SMARTNESS.memory_add("user", user_clean, emb_u)
        if assistant_clean:
            emb_a = _PROMPT_SMARTNESS.fetch_openai_style_embedding(host, model, assistant_clean, api_key)
            _PROMPT_SMARTNESS.memory_add("assistant", assistant_clean, emb_a)
    except Exception:
        # Memory is best-effort; never crash the conversation.
        return

def _generate_openai_style_reply(
    host: str,
    model: str,
    messages: list[dict[str, str]],
    api_key: str = "",
    tools: list[dict] | None = None,
    max_tool_rounds: int = 4,
) -> str:
    """Call the LLM, executing any tool_calls it returns until it produces text."""
    import sys
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    msgs: list[dict] = list(messages)

    for _round in range(max(1, max_tool_rounds)):
        payload: dict[str, object] = {
            "model": model.strip() or "gpt-4.1-mini",
            "messages": msgs,
            "temperature": 0.8,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        response = _http_post_json(
            f"{_api_url_from_host(host)}/v1/chat/completions",
            payload,
            timeout=240.0,
            headers=headers,
        )
        choices = response.get("choices", [])
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("LLM endpoint returned no choices.")
        first = choices[0]
        if not isinstance(first, dict):
            raise RuntimeError("LLM endpoint returned no assistant text.")

        message = first.get("message", {})
        finish_reason = str(first.get("finish_reason", "")).strip()

        # --- tool_calls branch ---
        tool_calls = []
        if isinstance(message, dict):
            tool_calls = message.get("tool_calls") or []

        if tool_calls and finish_reason in ("tool_calls", "", "stop"):
            # Append the assistant turn with tool_calls
            msgs.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": tool_calls})
            # Execute each tool and append results
            try:
                skills_dir = str(__file__).replace("hanauta_aipopup/tts.py", "skills")
                sys.path.insert(0, str(__file__).replace("/hanauta_aipopup/tts.py", ""))
                import skills as _skills
            except Exception:
                _skills = None  # type: ignore[assignment]

            for tc in tool_calls:
                if not isinstance(tc, dict):
                    continue
                tc_id = tc.get("id", "")
                fn = tc.get("function", {})
                fn_name = str(fn.get("name", "")).strip()
                try:
                    fn_args = json.loads(fn.get("arguments") or "{}")
                except Exception:
                    fn_args = {}
                if _skills is not None:
                    result = _skills.call(fn_name, fn_args)
                else:
                    result = f"[skills] registry unavailable for tool: {fn_name}"
                LOGGER.info("tool_call %s(%s) -> %s", fn_name, fn_args, result[:120])
                msgs.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": str(result),
                })
            continue  # next round: send tool results back to LLM

        # --- normal text reply ---
        if isinstance(message, dict):
            text = str(message.get("content", "")).strip()
            if text:
                return text
        text = str(first.get("text", "")).strip()
        if text:
            return text

    raise RuntimeError("LLM endpoint returned no assistant text after tool rounds.")


def _iter_openai_sse_deltas(url: str, payload: dict[str, object], headers: dict[str, str], timeout: float = 240.0):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    merged = dict(headers)
    merged.setdefault("Content-Type", "application/json")
    merged.setdefault("Accept", "text/event-stream")
    req = request.Request(url, data=body, headers=merged, method="POST")
    try:
        resp = request.urlopen(req, timeout=timeout)
    except Exception as exc:
        raise RuntimeError(str(exc).strip() or "LLM stream connection failed.") from exc
    with resp:
        for raw_line in resp:
            try:
                line = raw_line.decode("utf-8", "ignore").strip()
            except Exception:
                continue
            if not line or not line.startswith("data:"):
                continue
            data = line.split(":", 1)[1].strip()
            if not data:
                continue
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            choices = obj.get("choices", [])
            if not isinstance(choices, list) or not choices:
                continue
            first = choices[0]
            if not isinstance(first, dict):
                continue
            delta = first.get("delta", {})
            if isinstance(delta, dict):
                chunk = str(delta.get("content", "")).strip("\r")
                if chunk:
                    yield chunk
                    continue
            chunk = str(first.get("text", "")).strip("\r")
            if chunk:
                yield chunk


def _stream_openai_style_reply(
    host: str,
    model: str,
    messages: list[dict[str, str]],
    api_key: str = "",
):
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    payload: dict[str, object] = {
        "model": model.strip() or "gpt-4.1-mini",
        "messages": messages,
        "temperature": 0.8,
        "stream": True,
    }
    url = f"{_api_url_from_host(host)}/v1/chat/completions"
    yield from _iter_openai_sse_deltas(url, payload, headers, timeout=240.0)


def _tools_system_prompt(tools: list[dict]) -> str:
    """Render tool definitions as plain text for models that don't support native tool calling."""
    if not tools:
        return ""
    lines = [
        "You have access to the following tools. To use a tool, output ONLY a JSON block on its own line:",
        '  {"tool": "<tool_name>", "args": {<arguments>}}',
        "After the tool result is shown, continue your reply normally. Available tools:",
        "",
    ]
    for t in tools:
        fn = t.get("function", t)
        name = fn.get("name", "")
        desc = fn.get("description", "")
        params = fn.get("parameters", {}).get("properties", {})
        param_str = ", ".join(
            f"{k} ({v.get('type','any')}): {v.get('description','')}"
            for k, v in params.items()
        )
        lines.append(f"- {name}: {desc}" + (f"  Args: {param_str}" if param_str else ""))
    return "\n".join(lines)


def _parse_prompt_tool_call(text: str) -> tuple[str, dict] | None:
    """Extract {"tool": ..., "args": ...} from a model text reply. Returns (name, args) or None."""
    import re
    # Find all {...} blocks (including nested) and check each for a "tool" key
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                candidate = text[start:i + 1]
                try:
                    obj = json.loads(candidate)
                    name = str(obj.get("tool", "")).strip()
                    args = obj.get("args", obj.get("arguments", {}))
                    if name and isinstance(args, dict):
                        return name, args
                except Exception:
                    pass
                start = -1
    return None


def _generate_prompt_based_tool_reply(
    host: str,
    model: str,
    messages: list[dict],
    api_key: str,
    tools: list[dict],
    max_rounds: int = 4,
) -> str:
    """Tool-calling loop for backends that don't support native tool_calls (e.g. KoboldCpp)."""
    msgs = list(messages)
    for _round in range(max(1, max_rounds)):
        text = _generate_openai_style_reply(host, model, msgs, api_key)  # no tools= here
        parsed = _parse_prompt_tool_call(text)
        if parsed is None:
            return text  # plain reply, no tool call detected
        tool_name, tool_args = parsed
        try:
            import sys
            import importlib.util as _ilu
            skills_path = Path(__file__).parent.parent / "skills" / "__init__.py"
            spec = _ilu.spec_from_file_location("skills", skills_path)
            _sk = _ilu.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(_sk)  # type: ignore[union-attr]
            sys.modules["skills"] = _sk
            result = _sk.call(tool_name, tool_args)
        except Exception as exc:
            result = f"[skill error] {exc}"
        LOGGER.info("prompt tool_call %s(%s) -> %s", tool_name, tool_args, str(result)[:120])
        msgs.append({"role": "assistant", "content": text})
        msgs.append({"role": "user", "content": f"Tool result for {tool_name}:\n{result}"})
    return _generate_openai_style_reply(host, model, msgs, api_key)


def _load_skills() -> list[dict]:
    """Return skill tool definitions, or [] if skills are unavailable."""
    try:
        import sys
        import importlib.util
        skills_path = Path(__file__).parent.parent / "skills" / "__init__.py"
        if not skills_path.exists():
            return []
        spec = importlib.util.spec_from_file_location("skills", skills_path)
        if spec is None or spec.loader is None:
            return []
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        sys.modules["skills"] = mod
        return mod.tool_definitions()
    except Exception as exc:
        LOGGER.debug("Skills not loaded: %s", exc)
        return []


def generate_voice_chat_reply(
    config: dict[str, object],
    profiles: dict[str, BackendProfile],
    backend_settings: dict[str, dict[str, object]],
    prompt: str,
    character: CharacterCard | None,
) -> tuple[str, str, str, str]:
    privacy_mapping: dict[str, str] = {}
    masked_prompt = prompt
    # Auto-update emotion engine from the user's message
    try:
        import importlib.util as _ilu
        from pathlib import Path as _P
        _ep = _P(__file__).parent.parent / "skills" / "py-emotion-engine.py"
        if _ep.exists():
            _spec = _ilu.spec_from_file_location("skills.emotion_engine", _ep)
            _em = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
            _spec.loader.exec_module(_em)  # type: ignore[union-attr]
            _em.dispatch("emotion_update", {"source_text": prompt})
    except Exception:
        pass
    if bool(config.get("privacy_word_coding_enabled", False)):
        masked_prompt, privacy_mapping = _replace_sensitive_words(prompt, _privacy_word_list(config))
    memo = ""
    try:
        memo = _voice_memory_recall(config, masked_prompt)
    except Exception:
        memo = ""
    prompt_for_llm = masked_prompt
    try:
        if _voice_token_saver_enabled(config, profiles, backend_settings):
            prompt_for_llm = _compress_voice_prompt(masked_prompt, config)
    except Exception:
        prompt_for_llm = masked_prompt
    tools = _load_skills() if bool(config.get("skills_enabled", True)) else []
    from .user_profile import load_profile_state, preferred_user_name, load_ai_popup_user_profile
    _user_name = preferred_user_name(load_profile_state())
    _user_profile = load_ai_popup_user_profile()
    _user_info = _user_profile.get("about", "") if _user_profile.get("enabled", False) else ""
    messages = _chat_messages_with_memory(
        prompt_for_llm,
        character,
        emotion_tags=bool(config.get("emotion_tags_enabled", False)),
        memory=memo,
        tools=tools or None,
        user_name=_user_name,
        user_info=_user_info,
    )
    if bool(config.get("llm_external_api", False)):
        host = str(config.get("llm_host", "")).strip()
        model = str(config.get("llm_model", "")).strip() or "gpt-4.1-mini"
        text = _generate_openai_style_reply(
            host,
            model,
            messages,
            secure_load_secret("voice_mode:llm_api_key").strip(),
            tools=tools or None,
        )
        restored = _restore_sensitive_words(text, privacy_mapping)
        emotion, cleaned = _extract_emotion_and_clean_text(restored)
        _voice_memory_store_pair(config, masked_prompt, cleaned)
        return cleaned, "OpenAI-compatible", model, emotion

    profile_key = str(config.get("llm_profile", "koboldcpp")).strip()
    profile = profiles.get(profile_key)
    if profile is None:
        raise RuntimeError("Select a valid text backend for voice mode.")
    payload = dict(backend_settings.get(profile.key, {}))
    if profile.key == "ollama":
        host = str(payload.get("host", profile.host)).strip()
        model = str(payload.get("model", profile.model)).strip() or profile.model
        response = _http_post_json(
            f"{_api_url_from_host(host)}/api/chat",
            {"model": model, "messages": messages, "stream": False},
            timeout=240.0,
        )
        message = response.get("message", {})
        if isinstance(message, dict):
            text = str(message.get("content", "")).strip()
            if text:
                restored = _restore_sensitive_words(text, privacy_mapping)
                emotion, cleaned = _extract_emotion_and_clean_text(restored)
                return cleaned, profile.label, model, emotion
        raise RuntimeError("Ollama returned no assistant text.")
    if profile.provider in {"openai", "openai_compat"}:
        host = str(payload.get("host", profile.host)).strip()
        model = str(payload.get("model", profile.model)).strip() or profile.model
        api_key = secure_load_secret(f"{profile.key}:api_key").strip()
        text = _generate_openai_style_reply(host, model, messages, api_key, tools=tools or None)
        if profile.key == "koboldcpp":
            gguf_path = _existing_path(payload.get("gguf_path"))
            if gguf_path is not None:
                model = gguf_path.name
        restored = _restore_sensitive_words(text, privacy_mapping)
        emotion, cleaned = _extract_emotion_and_clean_text(restored)
        _voice_memory_store_pair(config, masked_prompt, cleaned)
        return cleaned, profile.label, model, emotion
    raise RuntimeError("Voice mode supports KoboldCpp/OpenAI-compatible, OpenAI-style, and Ollama text backends.")


def _resolve_hanauta_service_binary() -> Path | None:
    candidates = [
        APP_DIR.parent / "bin" / "hanauta-service",
        Path.home() / ".config" / "i3" / "hanauta" / "bin" / "hanauta-service",
    ]
    for candidate in candidates:
        path = candidate.expanduser()
        if path.exists() and os.access(path, os.X_OK):
            return path
    return None


def _waveform_from_hanauta_service(audio_path: Path, bars: int = 32) -> list[int]:
    key = str(audio_path.expanduser().resolve())
    cached = _WAVEFORM_CACHE.get(key)
    if cached:
        return list(cached)
    binary = _resolve_hanauta_service_binary()
    if binary is None:
        return []
    try:
        result = subprocess.run(
            [str(binary), "--waveform", key, str(max(8, min(128, int(bars))))],
            capture_output=True,
            text=True,
            timeout=6,
            check=True,
        )
        payload = json.loads((result.stdout or "").strip() or "{}")
        raw = payload.get("bars", []) if isinstance(payload, dict) else []
        if not isinstance(raw, list):
            return []
        cleaned = [max(0, min(100, int(v))) for v in raw if isinstance(v, (int, float, str))]
        if cleaned:
            _WAVEFORM_CACHE[key] = list(cleaned)
        return cleaned
    except Exception:
        return []


def _hf_resolve_url(repo_id: str, rel_path: str) -> str:
    clean_repo = repo_id.strip().strip("/")
    clean_file = rel_path.lstrip("/")
    return f"https://huggingface.co/{clean_repo}/resolve/main/{clean_file}?download=true"


def _download_file(
    url: str,
    destination: Path,
    timeout: float = 300.0,
    progress_cb: callable | None = None,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    attempts = 4
    for attempt in range(1, attempts + 1):
        try:
            req = request.Request(url, headers={"User-Agent": "Hanauta AI/1.0"})
            with request.urlopen(req, timeout=timeout) as response, destination.open("wb") as handle:
                total = int(response.headers.get("Content-Length", "0") or 0)
                written = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    written += len(chunk)
                    if callable(progress_cb):
                        progress_cb(written, total)
            return
        except Exception:
            if attempt >= attempts:
                raise
            time.sleep(min(4.0, 0.8 * attempt))


def _download_hf_files(
    repo_id: str,
    files: list[str],
    destination_root: Path,
    progress_cb: callable | None = None,
) -> None:
    total_files = max(1, len(files))
    completed = 0
    for rel_path in files:
        destination = destination_root / rel_path
        if destination.exists() and destination.stat().st_size > 0:
            completed += 1
            if callable(progress_cb):
                progress_cb(completed, total_files, rel_path)
            continue
        _download_file(_hf_resolve_url(repo_id, rel_path), destination)
        completed += 1
        if callable(progress_cb):
            progress_cb(completed, total_files, rel_path)


def _download_and_extract_zip_bundle(
    bundle_url: str,
    destination_root: Path,
    progress_cb: callable | None = None,
) -> None:
    destination_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hanauta-ai-tts-") as tmp:
        archive_path = Path(tmp) / "bundle.zip"

        def _bundle_progress(written: int, total: int) -> None:
            if not callable(progress_cb):
                return
            if total > 0:
                ratio = max(0.0, min(1.0, written / float(total)))
                progress_cb(int(ratio * 80), 100, "Downloading bundle")
            else:
                progress_cb(30, 100, "Downloading bundle")

        _download_file(bundle_url, archive_path, timeout=600.0, progress_cb=_bundle_progress)
        if callable(progress_cb):
            progress_cb(85, 100, "Extracting bundle")
        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            zip_ref.extractall(destination_root)
        entries = [entry for entry in destination_root.iterdir() if entry.name not in {".DS_Store", "__MACOSX"}]
        if len(entries) == 1 and entries[0].is_dir():
            nested_root = entries[0]
            for child in list(nested_root.iterdir()):
                target = destination_root / child.name
                if target.exists():
                    if target.is_dir():
                        shutil.rmtree(target, ignore_errors=True)
                    else:
                        target.unlink(missing_ok=True)
                shutil.move(str(child), str(target))
            shutil.rmtree(nested_root, ignore_errors=True)
        if callable(progress_cb):
            progress_cb(100, 100, "Bundle extracted")


def _kokoro_required_files(voice_name: str) -> list[str]:
    voice = voice_name.strip() or "af_bella"
    return [
        "config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "onnx/model_q8f16.onnx",
        f"voices/{voice}.bin",
    ]


def _pocket_required_files() -> list[str]:
    return [
        "pocket_tts_onnx.py",
        "tokenizer.model",
        "reference_sample.wav",
        "onnx/mimi_encoder.onnx",
        "onnx/text_conditioner.onnx",
        "onnx/flow_lm_main_int8.onnx",
        "onnx/flow_lm_flow_int8.onnx",
        "onnx/mimi_decoder_int8.onnx",
    ]


def _ensure_wav_reference(reference_path: Path) -> Path:
    source = reference_path.expanduser()
    if not source.exists():
        raise RuntimeError(f"Reference audio file not found: {source}")
    if source.suffix.lower() == ".wav":
        return source
    if shutil.which("ffmpeg") is None and shutil.which("sox") is None:
        raise RuntimeError("Install ffmpeg (recommended) or sox to convert reference audio to WAV.")

    POCKETTTS_REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    key = f"{str(source.resolve())}|{int(source.stat().st_mtime)}|{int(source.stat().st_size)}".encode("utf-8", "ignore")
    digest = hashlib.sha1(key).hexdigest()[:10]
    out = POCKETTTS_REFERENCE_DIR / f"{source.stem}_{digest}.wav"
    if out.exists():
        return out

    if shutil.which("ffmpeg") is not None:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-ac",
            "1",
            "-ar",
            "24000",
            str(out),
        ]
    else:
        cmd = [
            "sox",
            str(source),
            "-c",
            "1",
            "-r",
            "24000",
            str(out),
        ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=90)
    if result.returncode != 0 or not out.exists():
        detail = (result.stderr or result.stdout or "").strip().splitlines()[-8:]
        raise RuntimeError(f"Audio conversion failed:\n" + "\n".join(detail).strip())
    return out


def _tts_venv_dir(profile_key: str) -> Path:
    return AI_STATE_DIR / "tts-venvs" / profile_key


def _tts_venv_python(profile_key: str) -> Path:
    venv = _tts_venv_dir(profile_key)
    return venv / "bin" / "python3"


def _tts_engine_requirements(profile_key: str) -> list[str]:
    if profile_key == "kokorotts":
        return ["onnxruntime", "kokoro-onnx", "numpy"]
    if profile_key == "pockettts":
        return ["onnxruntime", "numpy", "sentencepiece", "soundfile", "scipy"]
    return []


def _system_language_code() -> str:
    try:
        code = str(QLocale.system().name() or "").split("_", 1)[0].strip().lower()
    except Exception:
        code = ""
    return code


def _default_pocket_language(payload: dict[str, object]) -> str:
    configured = str(payload.get("tts_language", "")).strip().lower()
    legacy = {
        "en": "english",
        "fr": "french",
        "de": "german",
        "pt": "portuguese",
        "it": "italian",
        "es": "spanish",
    }
    if configured in legacy:
        configured = legacy[configured]
    if configured in POCKETTTS_LANGUAGE_CODES:
        return configured
    system_code = _system_language_code()
    sys_map = {
        "en": "english",
        "fr": "french",
        "de": "german",
        "pt": "portuguese",
        "it": "italian",
        "es": "spanish",
    }
    mapped = sys_map.get(system_code, "")
    if mapped in POCKETTTS_LANGUAGE_CODES:
        return mapped
    if "english" in POCKETTTS_LANGUAGE_CODES:
        return "english"
    return "auto"


def _ensure_tts_runtime_venv(
    profile_key: str,
    *,
    progress_cb: callable | None = None,
) -> Path:
    requirements = _tts_engine_requirements(profile_key)
    if not requirements:
        raise RuntimeError(f"No runtime requirements declared for {profile_key}.")
    venv_dir = _tts_venv_dir(profile_key)
    python_bin = _tts_venv_python(profile_key)
    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    if not python_bin.exists():
        if callable(progress_cb):
            progress_cb(5, 100, "Creating virtualenv")
        result = subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        if result.returncode != 0 or not python_bin.exists():
            detail = (result.stderr or result.stdout or "").strip().splitlines()[-10:]
            raise RuntimeError("Failed to create virtualenv:\n" + "\n".join(detail).strip())
    if callable(progress_cb):
        progress_cb(20, 100, "Upgrading pip")
    subprocess.run(
        [str(python_bin), "-m", "pip", "install", "-U", "pip", "setuptools", "wheel"],
        capture_output=True,
        text=True,
        check=False,
        timeout=240,
    )
    if callable(progress_cb):
        progress_cb(35, 100, "Installing runtime dependencies")
    result = subprocess.run(
        [str(python_bin), "-m", "pip", "install", *requirements],
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()[-12:]
        raise RuntimeError("Runtime dependency install failed:\n" + "\n".join(detail).strip())
    if callable(progress_cb):
        progress_cb(100, 100, "Runtime ready")
    return python_bin


def _list_kokoro_voice_names(model_dir: Path) -> list[str]:
    voices_dir = model_dir / "voices"
    names: list[str] = []
    if voices_dir.exists():
        for voice_file in sorted(voices_dir.glob("*.bin")):
            names.append(voice_file.stem)
    if names:
        return names
    return [
        "af_bella",
        "af_nicole",
        "af_sarah",
        "af_sky",
        "am_adam",
        "am_michael",
        "bf_emma",
        "bf_isabella",
        "bm_george",
        "bm_lewis",
        "pf_dora",
        "pm_alex",
        "pm_santa",
    ]


def _list_pocket_voice_references(model_dir: Path) -> list[tuple[str, str]]:
    voices: list[tuple[str, str]] = []
    voices_dir = model_dir / "voices"
    if voices_dir.exists():
        for wav in sorted(voices_dir.rglob("*.wav")):
            try:
                rel = wav.relative_to(voices_dir).as_posix()
            except Exception:
                rel = wav.name
            label = wav.stem if rel == wav.name else f"{wav.stem} ({rel})"
            voices.append((label, str(wav)))
    reference = model_dir / "reference_sample.wav"
    if reference.exists():
        voices.insert(0, ("Default (reference_sample.wav)", str(reference)))
    if not voices:
        for wav in sorted(model_dir.glob("*.wav")):
            voices.append((wav.name, str(wav)))
    if not voices:
        return [("Select a WAV…", "")]
    return voices


def _pocket_preset_voice_path(model_dir: Path, preset_name: str) -> Path:
    safe_name = _safe_slug(preset_name.strip().lower() or "voice")
    return model_dir / "voices" / "kyutai" / f"{safe_name}.wav"


def _ensure_pocket_preset_voice(
    model_dir: Path,
    preset_name: str,
    *,
    progress_cb: callable | None = None,
) -> Path:
    rel = next((path for name, path in POCKETTTS_PRESET_VOICES if name == preset_name), "")
    if not rel:
        raise RuntimeError(f"Unknown PocketTTS preset voice: {preset_name}")
    target = _pocket_preset_voice_path(model_dir, preset_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 0:
        return target
    if callable(progress_cb):
        progress_cb(0, 1, f"Downloading {preset_name}")
    _download_hf_files(POCKETTTS_VOICES_REPO, [rel], target.parent, progress_cb=progress_cb)
    downloaded_candidates = [
        target.parent / rel,
        target.parent / Path(rel).name,
    ]
    downloaded: Path | None = None
    for candidate in downloaded_candidates:
        if candidate.exists():
            downloaded = candidate
            break
    if downloaded is None:
        for found in sorted(target.parent.rglob(Path(rel).name)):
            if found.is_file() and found.stat().st_size > 0:
                downloaded = found
                break
    if downloaded is not None and downloaded.exists():
        try:
            shutil.move(str(downloaded), str(target))
        except Exception:
            try:
                shutil.copy2(str(downloaded), str(target))
            except Exception:
                pass
    if not target.exists():
        # Fallback: keep original filename in-place (debuggability)
        if downloaded is not None and downloaded.exists():
            return downloaded
        raise RuntimeError(f"Failed to download preset voice: {preset_name}")
    return target


def _ensure_all_pocket_preset_voices(
    model_dir: Path,
    *,
    progress_cb: callable | None = None,
) -> None:
    total = max(1, len(POCKETTTS_PRESET_VOICES))
    done = 0
    for preset_name, _rel in POCKETTTS_PRESET_VOICES:
        if callable(progress_cb):
            progress_cb(done, total, f"{preset_name}")
        _ensure_pocket_preset_voice(model_dir, preset_name)
        done += 1
        if callable(progress_cb):
            progress_cb(done, total, f"{preset_name}")


def _default_tts_mode(payload: dict[str, object]) -> str:
    mode = str(payload.get("tts_mode", "")).strip().lower()
    if mode in {"local_onnx", "external_api"}:
        return mode
    host = str(payload.get("host", "")).strip()
    return "external_api" if host else "local_onnx"


def _default_tts_repo(profile: BackendProfile, payload: dict[str, object]) -> str:
    configured = str(payload.get("tts_model_repo", "")).strip()
    if configured:
        return configured
    if profile.key == "pockettts":
        return POCKET_ONNX_REPO
    return KOKORO_ONNX_REPO


def _default_tts_bundle_url(profile: BackendProfile, payload: dict[str, object]) -> str:
    configured = str(payload.get("tts_bundle_url", "")).strip()
    if configured:
        return configured
    if profile.key == "kokorotts":
        return KOKORO_TTS_RELEASE_URL
    return ""


def _default_tts_model_dir(profile: BackendProfile, payload: dict[str, object]) -> Path:
    configured = str(payload.get("binary_path", "")).strip()
    if configured:
        return Path(configured).expanduser()
    return TTS_MODELS_DIR / profile.key


def _ensure_tts_assets(
    profile: BackendProfile,
    payload: dict[str, object],
    *,
    download_if_missing: bool,
    progress_cb: callable | None = None,
) -> tuple[Path, str]:
    model_dir = _default_tts_model_dir(profile, payload)
    repo_id = _default_tts_repo(profile, payload)
    voice = str(payload.get("model", profile.model)).strip() or profile.model
    if profile.key == "pockettts":
        required = _pocket_required_files()
    else:
        required = _kokoro_required_files(voice)
    missing = [rel for rel in required if not (model_dir / rel).exists()]
    bundle_url = _default_tts_bundle_url(profile, payload)
    if missing and download_if_missing and bundle_url:
        _download_and_extract_zip_bundle(bundle_url, model_dir, progress_cb=progress_cb)
        missing = [rel for rel in required if not (model_dir / rel).exists()]
    if missing and not download_if_missing:
        raise RuntimeError(f"Missing model files in {model_dir}: {', '.join(missing[:3])}")
    if missing:
        _download_hf_files(repo_id, required, model_dir, progress_cb=progress_cb)
    return model_dir, voice


def _generate_kokoro_audio(
    model_dir: Path,
    voice: str,
    text: str,
    output_path: Path,
) -> None:
    _ensure_kokoro_runtime_dependencies()
    import numpy as np
    import onnxruntime as rt
    from kokoro_onnx.config import MAX_PHONEME_LENGTH, SAMPLE_RATE
    from kokoro_onnx.tokenizer import Tokenizer

    session = rt.InferenceSession(
        str(model_dir / "onnx" / "model_q8f16.onnx"),
        providers=["CPUExecutionProvider"],
    )
    tokenizer = Tokenizer(vocab={})
    phonemes = tokenizer.phonemize(text, "en-us")
    phonemes = phonemes[:MAX_PHONEME_LENGTH]
    token_ids = np.array(tokenizer.tokenize(phonemes), dtype=np.int64)
    if token_ids.size == 0:
        raise RuntimeError("No phonemes generated for input text.")
    voice_file = model_dir / "voices" / f"{voice}.bin"
    voice_data = np.fromfile(str(voice_file), dtype=np.float32)
    if voice_data.size == 0 or (voice_data.size % 256) != 0:
        raise RuntimeError(f"Voice file is not valid: {voice_file}")
    style = voice_data.reshape(-1, 1, 256)
    style_index = min(int(token_ids.size), int(style.shape[0]) - 1)
    style_vec = style[style_index]
    padded_tokens = [[0, *token_ids.tolist(), 0]]
    input_names = {entry.name for entry in session.get_inputs()}
    if "input_ids" in input_names:
        inputs = {
            "input_ids": padded_tokens,
            "style": np.array(style_vec, dtype=np.float32),
            "speed": np.array([1], dtype=np.int32),
        }
    else:
        inputs = {
            "tokens": padded_tokens,
            "style": np.array(style_vec, dtype=np.float32),
            "speed": np.ones(1, dtype=np.float32),
        }
    audio = session.run(None, inputs)[0].squeeze()
    if not isinstance(audio, np.ndarray) or audio.size == 0:
        raise RuntimeError("Kokoro ONNX returned empty audio.")
    _write_wav_from_float32_mono(output_path, audio.astype(np.float32), SAMPLE_RATE)


def _kokoro_synth_script_path() -> Path:
    return AI_STATE_DIR / "kokoro_synth_worker.py"


def _ensure_kokoro_synth_script() -> Path:
    script_path = _kokoro_synth_script_path()
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_text = """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import faulthandler
import os
from pathlib import Path
import traceback
import numpy as np
import onnxruntime as rt
from kokoro_onnx.config import MAX_PHONEME_LENGTH, SAMPLE_RATE
from kokoro_onnx.tokenizer import Tokenizer
import wave

STATE_DIR = Path.home() / ".local" / "state" / "hanauta" / "ai-popup"
LOG_PATH = STATE_DIR / "kokoro_synth_worker.log"


def _log(message: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(message.rstrip() + "\\n")


def write_wav(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    audio = np.clip(samples.astype(np.float32), -1.0, 1.0)
    pcm = (audio * 32767.0).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(int(sample_rate))
        wav.writeframes(pcm.tobytes())


def main() -> int:
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("ORT_NUM_THREADS", "1")
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    crash_fp = LOG_PATH.open("a", encoding="utf-8")
    faulthandler.enable(file=crash_fp, all_threads=True)
    _log("=== kokoro synth worker started ===")
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--voice", required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    model_dir = Path(args.model_dir).expanduser()
    output_path = Path(args.output).expanduser()
    _log(f"model_dir={model_dir}")
    _log(f"voice={args.voice}")
    _log(f"text_len={len(args.text or '')}")

    try:
        so = rt.SessionOptions()
        so.intra_op_num_threads = 1
        so.inter_op_num_threads = 1
        so.execution_mode = rt.ExecutionMode.ORT_SEQUENTIAL
        so.graph_optimization_level = rt.GraphOptimizationLevel.ORT_ENABLE_BASIC

        _log("creating ONNX session")
        session = rt.InferenceSession(
            str(model_dir / "onnx" / "model_q8f16.onnx"),
            sess_options=so,
            providers=["CPUExecutionProvider"],
        )
        _log("session created")

        tokenizer = Tokenizer(vocab={})
        phonemes = tokenizer.phonemize(args.text, "en-us")[:MAX_PHONEME_LENGTH]
        token_ids = np.array(tokenizer.tokenize(phonemes), dtype=np.int64)
        if token_ids.size == 0:
            raise RuntimeError("No phonemes generated for input text.")
        _log(f"token_count={int(token_ids.size)}")

        voice_file = model_dir / "voices" / f"{args.voice}.bin"
        voice_data = np.fromfile(str(voice_file), dtype=np.float32)
        if voice_data.size == 0 or (voice_data.size % 256) != 0:
            raise RuntimeError(f"Voice file is not valid: {voice_file}")
        _log(f"voice_floats={int(voice_data.size)}")

        style = voice_data.reshape(-1, 1, 256)
        style_index = min(int(token_ids.size), int(style.shape[0]) - 1)
        style_vec = style[style_index]
        padded_tokens = [[0, *token_ids.tolist(), 0]]

        session_inputs = {entry.name: entry for entry in session.get_inputs()}
        input_names = set(session_inputs.keys())
        speed_input = session_inputs.get("speed")
        speed_dtype = str(getattr(speed_input, "type", "") or "").lower() if speed_input is not None else ""
        if "input_ids" in input_names:
            inputs = {
                "input_ids": padded_tokens,
                "style": np.array(style_vec, dtype=np.float32),
            }
        else:
            inputs = {
                "tokens": padded_tokens,
                "style": np.array(style_vec, dtype=np.float32),
            }
        if "speed" in input_names:
            if "int" in speed_dtype:
                inputs["speed"] = np.array([1], dtype=np.int32)
            else:
                inputs["speed"] = np.ones(1, dtype=np.float32)

        _log("running session")
        audio = session.run(None, inputs)[0].squeeze()
        if not isinstance(audio, np.ndarray) or audio.size == 0:
            raise RuntimeError("Kokoro ONNX returned empty audio.")
        write_wav(output_path, audio.astype(np.float32), SAMPLE_RATE)
        _log(f"wrote output={output_path}")
        return 0
    except Exception as exc:
        _log(f"exception={exc}")
        _log(traceback.format_exc())
        raise


if __name__ == "__main__":
    raise SystemExit(main())
"""
    script_path.write_text(script_text, encoding="utf-8")
    try:
        os.chmod(script_path, 0o700)
    except Exception:
        pass
    return script_path


def _generate_kokoro_audio_subprocess(
    model_dir: Path,
    voice: str,
    text: str,
    output_path: Path,
) -> None:
    script_path = _ensure_kokoro_synth_script()
    python_bin = _tts_venv_python("kokorotts")
    python_exec = str(python_bin) if python_bin.exists() else sys.executable
    command = [
        python_exec,
        str(script_path),
        "--model-dir",
        str(model_dir),
        "--voice",
        voice,
        "--text",
        text,
        "--output",
        str(output_path),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        detail = stderr or stdout or "no output"
        if "No module named 'onnxruntime'" in detail or "No module named onnxruntime" in detail:
            raise RuntimeError(
                "Missing Kokoro runtime deps (onnxruntime). "
                "In Backend Settings, click 'Download TTS model' (it also installs runtime deps)."
            )
        if completed.returncode == -11:
            detail = (
                f"{detail}. Native segmentation fault in Kokoro worker. "
                f"See {KOKORO_SYNTH_LOG_FILE} for last checkpoint."
            )
        raise RuntimeError(
            f"Kokoro synth subprocess failed (exit {completed.returncode}). Detail: {detail}"
        )
    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise RuntimeError("Kokoro synth subprocess did not produce audio output.")


def _ensure_kokoro_runtime_dependencies() -> None:
    global _KOKORO_RUNTIME_READY
    if _KOKORO_RUNTIME_READY:
        return
    requirements: list[tuple[str, str]] = [
        ("onnxruntime", "onnxruntime>=1.19.0"),
        ("kokoro_onnx", "kokoro-onnx>=0.4.9"),
    ]
    missing_specs: list[str] = []
    for module_name, package_spec in requirements:
        try:
            importlib.import_module(module_name)
        except Exception:
            missing_specs.append(package_spec)
    if missing_specs:
        attempts: list[list[str]] = []
        uv_bin = shutil.which("uv")
        if uv_bin:
            attempts.append([uv_bin, "pip", "install", "--python", sys.executable, *missing_specs])
        attempts.append([sys.executable, "-m", "pip", "install", *missing_specs])
        attempts.append([sys.executable, "-m", "pip", "install", "--user", *missing_specs])
        errors: list[str] = []
        installed = False
        for command in attempts:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode == 0:
                installed = True
                break
            detail = (completed.stderr or completed.stdout or "").strip()
            errors.append(f"{' '.join(command)} => {detail or 'unknown error'}")
            if command[:3] == [sys.executable, "-m", "pip"]:
                ensure = subprocess.run(
                    [sys.executable, "-m", "ensurepip", "--upgrade"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if ensure.returncode == 0:
                    retry = subprocess.run(
                        command,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if retry.returncode == 0:
                        installed = True
                        break
                    retry_detail = (retry.stderr or retry.stdout or "").strip()
                    errors.append(f"{' '.join(command)} (after ensurepip) => {retry_detail or 'unknown error'}")
        if not installed:
            details = " | ".join(errors[-3:]) if errors else "no installer command available"
            raise RuntimeError(
                "Missing optional Kokoro runtime dependencies and automatic install failed. "
                f"Attempts: {details}"
            )
        for module_name, _ in requirements:
            importlib.import_module(module_name)
    _KOKORO_RUNTIME_READY = True


def _generate_pocket_audio(
    model_dir: Path,
    text: str,
    output_path: Path,
    voice_reference: str,
    language: str,
    voice_mode: str = "reference",
) -> None:
    script_path = _ensure_pocket_synth_script()
    python_bin = _tts_venv_python("pockettts")
    python_exec = str(python_bin) if python_bin.exists() else sys.executable
    command = [
        python_exec,
        str(script_path),
        "--model-dir",
        str(model_dir),
        "--text",
        text,
        "--output",
        str(output_path),
        "--language",
        str(language or "auto"),
    ]
    if str(voice_mode).strip().lower() != "none":
        reference = (
            Path(voice_reference).expanduser()
            if voice_reference.strip()
            else (model_dir / "reference_sample.wav")
        )
        reference = _ensure_wav_reference(reference)
        command.extend(["--voice-reference", str(reference)])
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        detail = stderr or stdout or "no output"
        if "No module named 'onnxruntime'" in detail or "No module named onnxruntime" in detail:
            raise RuntimeError(
                "Missing PocketTTS runtime deps (onnxruntime). "
                "In Backend Settings, click 'Install PocketTTS' (it also installs runtime deps)."
            )
        raise RuntimeError(f"PocketTTS synth failed (exit {completed.returncode}). Detail: {detail}")
    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise RuntimeError("PocketTTS synth did not produce audio output.")


def _pocket_synth_script_path() -> Path:
    return AI_STATE_DIR / "pocket_synth_worker.py"


def _ensure_pocket_synth_script() -> Path:
    script_path = _pocket_synth_script_path()
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_text = """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import wave

import numpy as np


def _write_wav(path: Path, samples: np.ndarray, sample_rate: int = 24000) -> None:
    audio = np.clip(samples.astype(np.float32), -1.0, 1.0)
    pcm = (audio * 32767.0).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(int(sample_rate))
        wav.writeframes(pcm.tobytes())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--voice-reference", default="")
    parser.add_argument("--language", default="auto")
    args = parser.parse_args()

    model_dir = Path(args.model_dir).expanduser()
    output_path = Path(args.output).expanduser()
    reference = Path(args.voice_reference).expanduser() if str(args.voice_reference or "").strip() else None

    script_path = model_dir / "pocket_tts_onnx.py"
    if not script_path.exists():
        raise RuntimeError(f"PocketTTS ONNX script not found: {script_path}")
    spec = importlib.util.spec_from_file_location("hanauta_pocket_tts_onnx", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load PocketTTS ONNX module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = module.PocketTTSOnnx(
        models_dir=str(model_dir / "onnx"),
        tokenizer_path=str(model_dir / "tokenizer.model"),
        precision="int8",
        device="auto",
    )
    lang = str(args.language or "").strip() or "auto"
    if reference is None:
        try:
            audio = engine.generate(args.text, language=lang)
        except TypeError:
            audio = engine.generate(args.text)
    else:
        try:
            audio = engine.generate(args.text, voice=str(reference), language=lang)
        except TypeError:
            audio = engine.generate(args.text, voice=str(reference))
    if not isinstance(audio, np.ndarray) or audio.size == 0:
        raise RuntimeError("PocketTTS returned empty audio.")
    _write_wav(output_path, audio.astype(np.float32), 24000)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""
    script_path.write_text(script_text, encoding="utf-8")
    try:
        os.chmod(script_path, 0o700)
    except Exception:
        pass
    return script_path




# ── KokoClone (voice cloning TTS) ────────────────────────────────────────────

_KOKOCLONE_VENV_KEY = "kokoclone"
_KOKOCLONE_REPO = "https://github.com/silasalves/kokoclone.git"
_KOKOCLONE_BRANCH = "official-kokoro"
_KOKOCLONE_INSTALL_DIR = AI_STATE_DIR / "kokoclone"


def _kokoclone_venv_dir() -> Path:
    return AI_STATE_DIR / "tts-venvs" / _KOKOCLONE_VENV_KEY


def _kokoclone_venv_python() -> Path:
    return _kokoclone_venv_dir() / "bin" / "python3"


def _kokoclone_worker_script_path() -> Path:
    return AI_STATE_DIR / "kokoclone_synth_worker.py"


def _ensure_kokoclone_installed(progress_cb=None) -> Path:
    """Clone the repo and install deps into an isolated venv. Returns python bin."""
    venv_dir = _kokoclone_venv_dir()
    python_bin = _kokoclone_venv_python()
    install_dir = _KOKOCLONE_INSTALL_DIR

    if callable(progress_cb):
        progress_cb(5, 100, "Cloning KokoClone repository")

    # Clone or update repo
    if not install_dir.exists():
        result = subprocess.run(
            ["git", "clone", "--branch", _KOKOCLONE_BRANCH, "--depth", "1",
             _KOKOCLONE_REPO, str(install_dir)],
            capture_output=True, text=True, timeout=120, check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git clone failed: {(result.stderr or result.stdout).strip()[-300:]}")
    else:
        subprocess.run(
            ["git", "-C", str(install_dir), "pull", "--ff-only"],
            capture_output=True, timeout=60, check=False,
        )

    if callable(progress_cb):
        progress_cb(20, 100, "Creating virtualenv")

    # Create venv
    if not python_bin.exists():
        result = subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            capture_output=True, text=True, timeout=120, check=False,
        )
        if result.returncode != 0 or not python_bin.exists():
            raise RuntimeError("Failed to create KokoClone venv.")

    if callable(progress_cb):
        progress_cb(30, 100, "Installing PyTorch (CPU)")

    # Install torch (CPU by default; GPU users can swap the index URL)
    subprocess.run(
        [str(python_bin), "-m", "pip", "install", "-q", "-U", "pip", "setuptools", "wheel"],
        capture_output=True, timeout=120, check=False,
    )
    torch_result = subprocess.run(
        [str(python_bin), "-m", "pip", "install", "-q",
         "torch", "torchaudio",
         "--index-url", "https://download.pytorch.org/whl/cpu"],
        capture_output=True, text=True, timeout=600, check=False,
    )
    if torch_result.returncode != 0:
        raise RuntimeError(f"torch install failed: {(torch_result.stderr or torch_result.stdout).strip()[-300:]}")

    if callable(progress_cb):
        progress_cb(60, 100, "Installing KokoClone requirements")

    req_file = install_dir / "requirements.txt"
    if req_file.exists():
        result = subprocess.run(
            [str(python_bin), "-m", "pip", "install", "-q", "-r", str(req_file)],
            capture_output=True, text=True, timeout=600, check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"requirements install failed: {(result.stderr or result.stdout).strip()[-300:]}")

    if callable(progress_cb):
        progress_cb(100, 100, "KokoClone ready")

    return python_bin


def _ensure_kokoclone_worker_script() -> Path:
    script_path = _kokoclone_worker_script_path()
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_text = r"""#!/usr/bin/env python3
"""
    script_text += r"""
import argparse
import sys
from pathlib import Path

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-dir", required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--lang", default="en")
    parser.add_argument("--reference", default="")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    install_dir = Path(args.install_dir)
    if str(install_dir) not in sys.path:
        sys.path.insert(0, str(install_dir))

    from core.cloner import KokoClone
    cloner = KokoClone()

    ref = args.reference.strip()
    if ref and Path(ref).exists():
        cloner.generate(
            text=args.text,
            lang=args.lang,
            reference_audio=ref,
            output_path=args.output,
        )
    else:
        # No reference: use plain Kokoro TTS without voice conversion
        import numpy as np
        import soundfile as sf
        pipeline = cloner._get_official_kokoro_pipeline(args.lang)
        _, voice = cloner._get_config(args.lang)
        samples, sr = cloner._synthesize_with_official_kokoro(pipeline, args.text, voice)
        sf.write(args.output, samples, sr)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
"""
    script_path.write_text(script_text, encoding="utf-8")
    try:
        os.chmod(script_path, 0o700)
    except Exception:
        pass
    return script_path


def _generate_kokoclone_audio(
    text: str,
    output_path: Path,
    lang: str = "en",
    reference_audio: str = "",
) -> None:
    """Generate speech via KokoClone (with optional voice cloning)."""
    python_bin = _kokoclone_venv_python()
    if not python_bin.exists():
        raise RuntimeError(
            "KokoClone is not installed. Click 'Install KokoClone' in Backend Settings."
        )
    install_dir = _KOKOCLONE_INSTALL_DIR
    if not install_dir.exists():
        raise RuntimeError(
            "KokoClone repository not found. Click 'Install KokoClone' in Backend Settings."
        )
    script_path = _ensure_kokoclone_worker_script()
    TTS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(python_bin), str(script_path),
        "--install-dir", str(install_dir),
        "--text", text,
        "--lang", lang,
        "--output", str(output_path),
    ]
    ref = str(reference_audio).strip()
    if ref and Path(ref).expanduser().exists():
        cmd += ["--reference", str(Path(ref).expanduser())]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "no output").strip()[-400:]
        raise RuntimeError(f"KokoClone synthesis failed: {detail}")
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("KokoClone produced no audio output.")

def synthesize_tts(
    profile: BackendProfile,
    payload: dict[str, object],
    text: str,
) -> tuple[Path, str]:
    mode = _default_tts_mode(payload)
    voice = str(payload.get("model", profile.model)).strip() or profile.model
    stamp = int(time.time() * 1000)
    out_name = f"{profile.key}_{stamp}_{_safe_slug(voice)}.wav"
    output_path = TTS_OUTPUT_DIR / out_name
    if mode == "external_api":
        host = str(payload.get("host", "")).strip()
        if not host:
            raise RuntimeError("External API mode requires a host URL.")
        api_key = secure_load_secret(f"{profile.key}:api_key").strip()
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        url = f"{_normalize_host_url(host)}/v1/audio/speech"
        body_payload: dict[str, object] = {
            "model": str(payload.get("tts_remote_model", payload.get("model", profile.model))).strip() or "tts-1",
            "input": text,
            "voice": voice,
        }
        if profile.key == "pockettts":
            lang = _default_pocket_language(payload)
            if lang and lang != "auto":
                body_payload["language"] = lang
        body, content_type = _http_post_bytes(
            url,
            body_payload,
            headers=headers,
            timeout=240.0,
        )
        if "application/json" in content_type.lower():
            parsed = json.loads(body.decode("utf-8"))
            audio_blob = parsed.get("audio")
            if isinstance(audio_blob, str) and audio_blob.strip():
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b64decode(audio_blob))
            else:
                raise RuntimeError("External API returned JSON without audio payload.")
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(body)
        return output_path, "external-api"

    model_dir, resolved_voice = _ensure_tts_assets(
        profile, payload, download_if_missing=bool(payload.get("tts_download_if_missing", True))
    )
    if profile.key == "pockettts":
        voice_mode = str(payload.get("tts_voice_mode", "reference")).strip().lower()
        preset = str(payload.get("tts_voice_preset", "")).strip().lower()
        voice_reference = str(payload.get("tts_voice_reference", "")).strip()
        if voice_mode != "none" and preset:
            try:
                voice_reference = str(_ensure_pocket_preset_voice(model_dir, preset))
            except Exception as exc:
                raise RuntimeError(f"Failed to fetch PocketTTS preset voice '{preset}': {exc}")
        _generate_pocket_audio(
            model_dir,
            text,
            output_path,
            voice_reference,
            _default_pocket_language(payload),
            voice_mode=voice_mode,
        )
    elif profile.key == "kokoclone":
        lang = str(payload.get("tts_language", "en")).strip() or "en"
        reference = str(payload.get("tts_voice_reference", "")).strip()
        # Per-character voice sample takes priority
        char_ref = str(payload.get("_character_voice_sample", "")).strip()
        if char_ref and Path(char_ref).expanduser().exists():
            reference = char_ref
        _generate_kokoclone_audio(text, output_path, lang=lang, reference_audio=reference)
    else:
        if profile.key == "kokorotts":
            _generate_kokoro_audio_subprocess(model_dir, resolved_voice, text, output_path)
        else:
            _generate_kokoro_audio(model_dir, resolved_voice, text, output_path)
    return output_path, "local-onnx"


def validate_backend(profile: BackendProfile, payload: dict[str, object]) -> tuple[bool, str]:
    host = str(payload.get("host", "")).strip()
    model = str(payload.get("model", "")).strip()
    api_key = secure_load_secret(f"{profile.key}:api_key")
    binary_path = _existing_path(payload.get("binary_path"))
    gguf_path = _existing_path(payload.get("gguf_path"))
    if not model:
        return False, "Model is required."
    if profile.needs_api_key and not api_key:
        return False, "API key is required."
    if not profile.needs_api_key and not host and not profile.launchable:
        return False, "Host is required."

    if profile.key == "koboldcpp":
        if binary_path is None:
            return False, "KoboldCpp binary path is required."
        if gguf_path is None:
            return False, "Select a GGUF model for KoboldCpp."
        if host and _openai_compat_alive(host):
            return True, "KoboldCpp is reachable."
        return True, "Launch config saved. Click the KoboldCpp icon to start it."

    if profile.provider == "tts_local":
        mode = _default_tts_mode(payload)
        if mode == "external_api":
            if not host:
                return False, "External API mode requires a host."
            return True, "External TTS endpoint saved."
        model_dir = _default_tts_model_dir(profile, payload)
        if profile.key == "pockettts":
            required = _pocket_required_files()
        else:
            voice = str(payload.get("model", profile.model)).strip() or profile.model
            required = _kokoro_required_files(voice)
        missing = [rel for rel in required if not (model_dir / rel).exists()]
        if not missing:
            return True, "Local ONNX model directory looks valid."
        if bool(payload.get("tts_download_if_missing", True)):
            return True, "Local ONNX mode is ready to download missing model files."
        preview = ", ".join(missing[:2])
        suffix = "..." if len(missing) > 2 else ""
        return False, f"Missing local ONNX files: {preview}{suffix}"

    if profile.provider == "sdwebui":
        url = _normalize_host_url(host)
        try:
            response = _http_json(
                f"{url}/sdapi/v1/samplers",
                timeout=3.0,
                headers=_sd_auth_headers(profile.key, payload),
            )
            if not isinstance(response, list):
                return False, "SD WebUI did not return samplers."
        except error.HTTPError as exc:
            if int(getattr(exc, "code", 0) or 0) == 404:
                return False, _sdapi_not_found_message(host)
            return False, f"SD WebUI request failed: HTTP {getattr(exc, 'code', 'error')}"
        except Exception:
            return False, "SD WebUI host did not respond."
        return True, "SD WebUI connection looks valid."

    if profile.provider == "openai_compat":
        url = _normalize_host_url(host)
        try:
            with request.urlopen(f"{url}/v1/models", timeout=2.5) as response:
                if response.status >= 400:
                    return False, f"HTTP {response.status}"
        except Exception:
            return False, "Host did not respond."
    elif profile.key == "ollama":
        url = _normalize_host_url(host)
        try:
            with request.urlopen(f"{url}/api/tags", timeout=2.5) as response:
                if response.status >= 400:
                    return False, f"HTTP {response.status}"
        except Exception:
            return False, "Host did not respond."

    return True, "Connection settings look valid."


def _start_kokoro_server(payload: dict[str, object]) -> tuple[bool, str]:
    try:
        command, source = _resolve_kokoro_server_command(payload)
    except Exception as exc:
        return False, str(exc)
    if source == "auto":
        payload["tts_server_command"] = shlex.join(command)
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as exc:
        return False, f"Unable to start Kokoro server: {exc}"
    payload["tts_server_pid"] = int(process.pid or 0)
    try:
        payload["tts_server_pgid"] = int(os.getpgid(int(process.pid or 0))) if int(process.pid or 0) else 0
    except Exception:
        payload["tts_server_pgid"] = int(payload.get("tts_server_pgid", 0) or 0)
    return True, f"Kokoro server started with: {' '.join(command)}"





def _host_reachable(host: str, timeout: float = 1.2) -> bool:
    text = host.strip()
    if not text:
        return False
    parsed = urlparse(text if "://" in text else f"http://{text}")
    hostname = parsed.hostname or ""
    port = int(parsed.port or 80)
    if not hostname:
        return False
    try:
        with socket.create_connection((hostname, port), timeout=timeout):
            return True
    except OSError:
        return False


def _parse_host_port(host: str) -> tuple[str, int]:
    raw = host.strip()
    if not raw:
        return "127.0.0.1", 8880
    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    hostname = parsed.hostname or "127.0.0.1"
    port = int(parsed.port or 8880)
    return hostname, port


def _kokoro_local_server_script_path() -> Path:
    return AI_STATE_DIR / "kokoro_local_server.py"


def _ensure_kokoro_local_server_script() -> Path:
    script_path = _kokoro_local_server_script_path()
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_text = """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import onnxruntime as rt
from kokoro_onnx.config import MAX_PHONEME_LENGTH, SAMPLE_RATE
from kokoro_onnx.tokenizer import Tokenizer


def _synth(model_dir: Path, text: str, voice: str) -> bytes:
    session = rt.InferenceSession(
        str(model_dir / "onnx" / "model_q8f16.onnx"),
        providers=["CPUExecutionProvider"],
    )
    tokenizer = Tokenizer(vocab={})
    phonemes = tokenizer.phonemize(text, "en-us")[:MAX_PHONEME_LENGTH]
    token_ids = np.array(tokenizer.tokenize(phonemes), dtype=np.int64)
    if token_ids.size == 0:
        raise RuntimeError("No phonemes generated.")
    voice_file = model_dir / "voices" / f"{voice}.bin"
    if not voice_file.exists():
        raise RuntimeError(f"Voice not found: {voice_file}")
    voice_data = np.fromfile(str(voice_file), dtype=np.float32)
    if voice_data.size == 0 or (voice_data.size % 256) != 0:
        raise RuntimeError(f"Invalid voice file: {voice_file}")
    style = voice_data.reshape(-1, 1, 256)
    style_idx = min(int(token_ids.size), int(style.shape[0]) - 1)
    style_vec = style[style_idx]
    padded_tokens = [[0, *token_ids.tolist(), 0]]
    input_names = {entry.name for entry in session.get_inputs()}
    if "input_ids" in input_names:
        inputs = {
            "input_ids": padded_tokens,
            "style": np.array(style_vec, dtype=np.float32),
            "speed": np.array([1], dtype=np.int32),
        }
    else:
        inputs = {
            "tokens": padded_tokens,
            "style": np.array(style_vec, dtype=np.float32),
            "speed": np.ones(1, dtype=np.float32),
        }
    audio = session.run(None, inputs)[0].squeeze()
    audio = np.clip(audio.astype(np.float32), -1.0, 1.0)
    pcm = (audio * 32767.0).astype(np.int16)
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(int(SAMPLE_RATE))
        wav.writeframes(pcm.tobytes())
    return out.getvalue()


def _handler(model_dir: Path, default_voice: str):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, code: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self._json(200, {"ok": True})
                return
            if self.path == "/v1/models":
                self._json(200, {"data": [{"id": "kokoro-local"}]})
                return
            self._json(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/v1/audio/speech":
                self._json(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except Exception:
                self._json(400, {"error": "invalid json"})
                return
            text = str(payload.get("input", "")).strip()
            voice = str(payload.get("voice", default_voice)).strip() or default_voice
            if not text:
                self._json(400, {"error": "input is required"})
                return
            try:
                wav = _synth(model_dir, text, voice)
            except Exception as exc:
                self._json(500, {"error": str(exc)})
                return
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(wav)))
            self.end_headers()
            self.wfile.write(wav)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8880)
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--voice", default="af_bella")
    args = parser.parse_args()
    model_dir = Path(args.model_dir).expanduser()
    server = ThreadingHTTPServer((args.host, args.port), _handler(model_dir, args.voice))
    server.serve_forever()


if __name__ == "__main__":
    main()
"""
    script_path.write_text(script_text, encoding="utf-8")
    try:
        os.chmod(script_path, 0o700)
    except Exception:
        pass
    return script_path


def _default_kokoro_server_command(payload: dict[str, object]) -> list[str] | None:
    try:
        _ensure_kokoro_runtime_dependencies()
    except Exception:
        return None
    model_dir = _default_tts_model_dir(
        BackendProfile("kokorotts", "KokoroTTS", "tts_local", "af_bella", "127.0.0.1:8880", "kokorotts"),
        payload,
    )
    if not model_dir.exists():
        return None
    host, port = _parse_host_port(str(payload.get("host", "127.0.0.1:8880")))
    voice = str(payload.get("model", "af_bella")).strip() or "af_bella"
    server_script = _ensure_kokoro_local_server_script()
    return [
        sys.executable,
        str(server_script),
        "--host",
        host,
        "--port",
        str(port),
        "--model-dir",
        str(model_dir),
        "--voice",
        voice,
    ]


def _resolve_kokoro_server_command(payload: dict[str, object]) -> tuple[list[str], str]:
    command_text = str(payload.get("tts_server_command", "")).strip()
    if command_text:
        try:
            return shlex.split(command_text), "custom"
        except Exception as exc:
            raise RuntimeError(f"Invalid server command: {exc}")
    candidate = _existing_path(payload.get("binary_path"))
    if candidate is not None and candidate.is_file() and os.access(candidate, os.X_OK):
        return [str(candidate)], "binary"
    auto = _default_kokoro_server_command(payload)
    if auto:
        return auto, "auto"
    raise RuntimeError(
        "No valid Kokoro server command was found. Download models first, or set 'TTS server command'."
    )


def _kokoro_server_status(payload: dict[str, object]) -> tuple[bool, str]:
    host = str(payload.get("host", "")).strip()
    if host:
        if _openai_compat_alive(host) or _host_reachable(host):
            return True, f"Server active at {host}"
    pid = int(payload.get("tts_server_pid", 0) or 0)
    if _is_pid_alive(pid):
        return True, f"Server process running (pid {pid})"
    return False, "Server inactive"


def _stop_kokoro_server(payload: dict[str, object]) -> tuple[bool, str]:
    pid = int(payload.get("tts_server_pid", 0) or 0)
    pgid = int(payload.get("tts_server_pgid", 0) or 0)
    if not _is_pid_alive(pid) and not _is_pgid_alive(pgid):
        payload["tts_server_pid"] = 0
        payload["tts_server_pgid"] = 0
        return False, "No tracked Kokoro server process is running."
    try:
        if _is_pgid_alive(pgid):
            os.killpg(pgid, signal.SIGTERM)
        elif _is_pid_alive(pid):
            os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        return False, f"Unable to stop Kokoro server: {exc}"
    payload["tts_server_pid"] = 0
    payload["tts_server_pgid"] = 0
    return True, f"Stopped Kokoro server process {pid}."





def _pocket_server_binary_path() -> Path:
    return POCKETTTS_SERVER_INSTALL_DIR / POCKETTTS_SERVER_BINARY_NAME


def _install_pockettts_server(progress_cb: callable | None = None) -> Path:
    if shutil.which("g++") is None:
        raise RuntimeError("g++ is required to build the PocketTTS server.")
    if not POCKETTTS_SERVER_SRC_DIR.exists():
        raise RuntimeError(f"PocketTTS server sources not found: {POCKETTTS_SERVER_SRC_DIR}")
    build_script = POCKETTTS_SERVER_SRC_DIR / "build.sh"
    if not build_script.exists():
        raise RuntimeError(f"Missing build script: {build_script}")
    if callable(progress_cb):
        progress_cb(5, 100, "Building PocketTTS server")
    result = subprocess.run(
        ["bash", str(build_script)],
        cwd=str(POCKETTTS_SERVER_SRC_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-8:]
        detail = "\n".join(tail).strip()
        raise RuntimeError(f"PocketTTS server build failed.\n{detail or 'unknown error'}")
    built_binary = POCKETTTS_SERVER_SRC_DIR / "build" / POCKETTTS_SERVER_BINARY_NAME
    if not built_binary.exists():
        raise RuntimeError(f"Built PocketTTS server binary not found: {built_binary}")
    POCKETTTS_SERVER_INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    target = _pocket_server_binary_path()
    shutil.copy2(built_binary, target)
    try:
        os.chmod(target, 0o755)
    except Exception:
        pass
    infer_src = POCKETTTS_SERVER_SRC_DIR / POCKETTTS_SERVER_INFER_SCRIPT_NAME
    if not infer_src.exists():
        raise RuntimeError(f"Missing PocketTTS infer helper script: {infer_src}")
    shutil.copy2(infer_src, POCKETTTS_SERVER_INSTALL_DIR / POCKETTTS_SERVER_INFER_SCRIPT_NAME)
    if callable(progress_cb):
        progress_cb(100, 100, "PocketTTS server installed")
    return target


def _parse_host_port_default(host: str, default_port: int) -> tuple[str, int]:
    raw = host.strip()
    if not raw:
        return "127.0.0.1", int(default_port)
    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    hostname = parsed.hostname or "127.0.0.1"
    port = int(parsed.port or default_port)
    return hostname, port


def _default_pocket_server_command(payload: dict[str, object]) -> list[str] | None:
    binary = _pocket_server_binary_path()
    if not (binary.exists() and os.access(binary, os.X_OK)):
        return None
    model_dir = _default_tts_model_dir(
        BackendProfile("pockettts", "PocketTTS", "tts_local", "pocket", "127.0.0.1:8890", "pockettts"),
        payload,
    )
    if not model_dir.exists():
        return None
    host, port = _parse_host_port_default(str(payload.get("host", "127.0.0.1:8890")), 8890)
    default_language = str(payload.get("tts_language", "")).strip() or "auto"
    return [
        str(binary),
        "--host",
        host,
        "--port",
        str(port),
        "--model-dir",
        str(model_dir),
        "--default-language",
        default_language,
    ]


def _resolve_pocket_server_command(payload: dict[str, object]) -> tuple[list[str], str]:
    command_text = str(payload.get("tts_server_command", "")).strip()
    if command_text:
        try:
            return shlex.split(command_text), "custom"
        except Exception as exc:
            raise RuntimeError(f"Invalid server command: {exc}")
    auto = _default_pocket_server_command(payload)
    if auto:
        return auto, "auto"
    raise RuntimeError(
        "No valid PocketTTS server command was found. Click Install PocketTTS first, or set 'TTS server command'."
    )


def _pocket_server_status(payload: dict[str, object]) -> tuple[bool, str]:
    host = str(payload.get("host", "")).strip()
    if host:
        if _openai_compat_alive(host) or _host_reachable(host):
            return True, f"Server active at {host}"
    pid = int(payload.get("tts_server_pid", 0) or 0)
    pgid = int(payload.get("tts_server_pgid", 0) or 0)
    if _is_pid_alive(pid) or _is_pgid_alive(pgid):
        return True, f"Server process running (pid {pid})"
    return False, "Server inactive"


def _start_pocket_server(payload: dict[str, object]) -> tuple[bool, str]:
    try:
        command, source = _resolve_pocket_server_command(payload)
    except Exception as exc:
        return False, str(exc)
    if source == "auto":
        payload["tts_server_command"] = shlex.join(command)
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as exc:
        return False, f"Unable to start PocketTTS server: {exc}"
    payload["tts_server_pid"] = int(process.pid or 0)
    try:
        payload["tts_server_pgid"] = int(os.getpgid(int(process.pid or 0))) if int(process.pid or 0) else 0
    except Exception:
        payload["tts_server_pgid"] = int(payload.get("tts_server_pgid", 0) or 0)
    return True, f"PocketTTS server started with: {' '.join(command)}"


def _stop_pocket_server(payload: dict[str, object]) -> tuple[bool, str]:
    pid = int(payload.get("tts_server_pid", 0) or 0)
    pgid = int(payload.get("tts_server_pgid", 0) or 0)
    if not _is_pid_alive(pid) and not _is_pgid_alive(pgid):
        payload["tts_server_pid"] = 0
        payload["tts_server_pgid"] = 0
        return False, "No tracked PocketTTS server process is running."
    try:
        if _is_pgid_alive(pgid):
            os.killpg(pgid, signal.SIGTERM)
        elif _is_pid_alive(pid):
            os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        return False, f"Unable to stop PocketTTS server: {exc}"
    payload["tts_server_pid"] = 0
    payload["tts_server_pgid"] = 0
    return True, f"Stopped PocketTTS server process {pid}."


def _pocket_systemd_user_service_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / "hanauta-pockettts.service"


def _write_pocket_systemd_service(payload: dict[str, object]) -> tuple[bool, str]:
    try:
        command, source = _resolve_pocket_server_command(payload)
    except Exception as exc:
        return False, str(exc)
    command_text = shlex.join(command)
    if source == "auto":
        payload["tts_server_command"] = command_text
    service_path = _pocket_systemd_user_service_path()
    service_path.parent.mkdir(parents=True, exist_ok=True)
    service_text = f"""[Unit]
Description=Hanauta PocketTTS Server
After=default.target

[Service]
Type=simple
ExecStart={command_text}
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
"""
    service_path.write_text(service_text, encoding="utf-8")
    result = _systemctl_user("daemon-reload")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return False, f"systemd reload failed: {detail or 'unknown error'}"
    return True, f"Service file written at {service_path}"


def _set_pocket_autostart(payload: dict[str, object], enabled: bool) -> tuple[bool, str]:
    if shutil.which("systemctl") is None:
        return False, "systemctl is not available on this system."
    if enabled:
        ok, msg = _write_pocket_systemd_service(payload)
        if not ok:
            return False, msg
        result = _systemctl_user("enable", "--now", "hanauta-pockettts.service")
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            return False, f"Failed to enable autostart: {detail or 'unknown error'}"
        return True, "PocketTTS autostart enabled."
    result = _systemctl_user("disable", "--now", "hanauta-pockettts.service")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        lowered = detail.lower()
        if "not loaded" not in lowered and "does not exist" not in lowered:
            return False, f"Failed to disable autostart: {detail or 'unknown error'}"
    return True, "PocketTTS autostart disabled."


def _kokoro_systemd_user_service_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / "hanauta-kokorotts.service"


def _systemctl_user(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _write_kokoro_systemd_service(payload: dict[str, object]) -> tuple[bool, str]:
    try:
        command, source = _resolve_kokoro_server_command(payload)
    except Exception as exc:
        return False, str(exc)
    command_text = shlex.join(command)
    if source == "auto":
        payload["tts_server_command"] = command_text
    service_path = _kokoro_systemd_user_service_path()
    service_path.parent.mkdir(parents=True, exist_ok=True)
    service_text = f"""[Unit]
Description=Hanauta KokoroTTS Server
After=default.target

[Service]
Type=simple
ExecStart={command_text}
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
"""
    service_path.write_text(service_text, encoding="utf-8")
    result = _systemctl_user("daemon-reload")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return False, f"systemd reload failed: {detail or 'unknown error'}"
    return True, f"Service file written at {service_path}"


def _set_kokoro_autostart(payload: dict[str, object], enabled: bool) -> tuple[bool, str]:
    if shutil.which("systemctl") is None:
        return False, "systemctl is not available on this system."
    if enabled:
        ok, msg = _write_kokoro_systemd_service(payload)
        if not ok:
            return False, msg
        result = _systemctl_user("enable", "--now", "hanauta-kokorotts.service")
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            return False, f"Failed to enable autostart: {detail or 'unknown error'}"
        return True, "Kokoro autostart enabled."
    result = _systemctl_user("disable", "--now", "hanauta-kokorotts.service")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        lowered = detail.lower()
        if "not loaded" not in lowered and "does not exist" not in lowered:
            return False, f"Failed to disable autostart: {detail or 'unknown error'}"
    return True, "Kokoro autostart disabled."



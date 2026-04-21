from __future__ import annotations

import os
import sys
from pathlib import Path


# Repo/plugin root (parent of this package).
PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def _resolve_hanauta_src() -> Path:
    env_hint = Path(str(os.environ.get("HANAUTA_SRC", "")).strip()).expanduser()
    candidates: list[Path] = []
    if str(env_hint).strip():
        candidates.append(env_hint)
    candidates.append(Path.home() / ".config" / "i3" / "hanauta" / "src")
    try:
        candidates.append(PLUGIN_ROOT.parents[1])
    except Exception:
        pass
    for parent in PLUGIN_ROOT.parents:
        candidates.append(parent / "hanauta" / "src")
        candidates.append(parent / "src")
    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except Exception:
            resolved = candidate.expanduser()
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        if (resolved / "pyqt" / "shared" / "theme.py").exists():
            return resolved
    return Path.home() / ".config" / "i3" / "hanauta" / "src"


APP_DIR = _resolve_hanauta_src()
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


from pyqt.shared.theme import load_theme_palette, palette_mtime, relative_luminance  # noqa: E402
from pyqt.shared.button_helpers import create_close_button  # noqa: E402

try:  # noqa: E402
    from pyqt.shared.plugin_bridge import trigger_fullscreen_alert
except Exception:  # noqa: E402

    def trigger_fullscreen_alert(title: str, body: str, severity: str = "discrete") -> bool:
        del title, body, severity
        return False


AI_ASSETS_DIR = (
    PLUGIN_ROOT / "assets"
    if (PLUGIN_ROOT / "assets" / "backend-icons").exists()
    else APP_DIR / "pyqt" / "ai-popup" / "assets"
)
BACKEND_ICONS_DIR = AI_ASSETS_DIR / "backend-icons"

AI_STATE_DIR = Path.home() / ".local" / "state" / "hanauta" / "ai-popup"
BACKEND_SETTINGS_FILE = AI_STATE_DIR / "backend_settings.json"
SECURE_DB_FILE = AI_STATE_DIR / "secure_store.sqlite3"
SECURE_KEY_FILE = AI_STATE_DIR / "secure_store.key"
IMAGE_OUTPUT_DIR = AI_STATE_DIR / "generated-images"
TTS_MODELS_DIR = AI_STATE_DIR / "tts-models"
TTS_OUTPUT_DIR = AI_STATE_DIR / "tts-audio"
VOICE_RECORDINGS_DIR = AI_STATE_DIR / "voice-recordings"
CHAT_ARCHIVES_DIR = AI_STATE_DIR / "chat-archives"
CHARACTER_LIBRARY_FILE = AI_STATE_DIR / "characters.json"
CHARACTER_AVATARS_DIR = AI_STATE_DIR / "characters-avatars"
VOICE_PRIVACY_CODEBOOK_FILE = AI_STATE_DIR / "voice-privacy-codebook.txt"
VOICE_TOKEN_COMPRESSOR_FILE = AI_STATE_DIR / "voice-token-compressor.json"
VOICE_MEMORY_DB_FILE = AI_STATE_DIR / "voice-memory.sqlite3"

NOTIFICATION_CENTER_STATE_DIR = Path.home() / ".local" / "state" / "hanauta" / "notification-center"
NOTIFICATION_CENTER_SETTINGS_FILE = NOTIFICATION_CENTER_STATE_DIR / "settings.json"

AI_POPUP_LOG_FILE = AI_STATE_DIR / "ai_popup.log"
AI_POPUP_ERROR_LOG_FILE = AI_STATE_DIR / "ai_popup-errors.log"
AI_POPUP_CRASH_FILE = AI_STATE_DIR / "ai_popup.crash.log"
KOKORO_SYNTH_LOG_FILE = AI_STATE_DIR / "kokoro_synth_worker.log"
KOBOLDCPP_RELEASE_STATE_FILE = AI_STATE_DIR / "koboldcpp-release-state.json"
MODEL_CATALOG_FILE = PLUGIN_ROOT / "model_catalog.json"
GGUF_GALLERY_DIR = AI_STATE_DIR / "gguf-gallery"

VOICE_STOP_EXPRESSIONS_FILE = PLUGIN_ROOT / "voice-stop-expressions.json"
VOICE_TOKEN_COMPRESSOR_SAMPLE_FILE = PLUGIN_ROOT / "voice-token-compressor.sample.json"

# Model repo metadata and local runtime paths (used by TTS download/install helpers).
KOKORO_ONNX_REPO = "onnx-community/Kokoro-82M-ONNX"
POCKET_ONNX_REPO = "KevinAHM/pocket-tts-onnx"
KOKORO_TTS_RELEASE_REPO = "gab-luz/hanauta"
KOKORO_TTS_RELEASE_TAG = "TTS"
KOKORO_TTS_RELEASE_ASSET = "kokorotts-quantized-bundle.zip"
KOKORO_TTS_RELEASE_URL = (
    f"https://github.com/{KOKORO_TTS_RELEASE_REPO}/releases/download/"
    f"{KOKORO_TTS_RELEASE_TAG}/{KOKORO_TTS_RELEASE_ASSET}"
)

POCKETTTS_SERVER_SRC_DIR = PLUGIN_ROOT / "onnx" / "cpp" / "pockettts_server"
POCKETTTS_SERVER_INSTALL_DIR = AI_STATE_DIR / "pockettts-server"
POCKETTTS_SERVER_BINARY_NAME = "pockettts_server"
POCKETTTS_SERVER_INFER_SCRIPT_NAME = "pockettts_infer.py"
POCKETTTS_REFERENCE_DIR = AI_STATE_DIR / "pockettts-references"
POCKETTTS_VOICES_REPO = "kyutai/tts-voices"
POCKETTTS_PRESET_VOICES: list[tuple[str, str]] = [
    ("alba", "alba-mackenna/casual.wav"),
    ("marius", "voice-donations/Selfie.wav"),
    ("javert", "voice-donations/Butter.wav"),
    ("jean", "ears/p010/freeform_speech_01.wav"),
    ("fantine", "vctk/p244_023.wav"),
    ("cosette", "expresso/ex04-ex02_confused_001_channel1_499s.wav"),
    ("eponine", "vctk/p262_023.wav"),
    ("azelma", "vctk/p303_023.wav"),
]
POCKETTTS_LANGUAGES: list[tuple[str, str]] = [
    ("Auto", "auto"),
    ("English", "english"),
    ("Français", "french"),
    ("Deutsch", "german"),
    ("Português", "portuguese"),
    ("Italiano", "italian"),
    ("Español", "spanish"),
]
POCKETTTS_LANGUAGE_CODES = {code for _label, code in POCKETTTS_LANGUAGES}

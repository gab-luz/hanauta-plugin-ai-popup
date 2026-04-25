# hanauta-plugin-ai-popup

A floating AI popup for the [Hanauta](https://github.com/hanauta) desktop — wallpaper-reactive, voice-enabled, tool-calling, and character-aware.

Runs on **PyQt6 + KoboldCpp / OpenAI-compatible backends**. No Electron, no cloud dependency by default.

---

## Features

- **Multi-backend chat** — KoboldCpp (Gemma 4, LLaMA, Mistral…), LM Studio, Ollama, OpenAI-compatible, Gemini
- **Voice mode** — hands-free STT → LLM → TTS loop with barge-in, end-of-speech detection, streaming
- **Tool calling / Skills** — 38+ tools across Docker, desktop, mail, KDE Connect, sensors, notifications, and more
- **Emotion engine** — infers user emotional state from text; all skills and AI tone adapt automatically
- **NSFL safety guard** — blocks dangerous physical actions; double fullscreen confirmation for high-risk ones (garage doors, locks, stoves…)
- **Character cards** — TavernAI/KoboldCpp `.json` and `.png` format; `{{user}}` / `{{char}}` template resolution
- **Wallpaper-reactive theming** — live Matugen palette applied to the popup
- **Encrypted storage** — chat history and secrets stored with Fernet encryption

---

## Architecture

```
ai_popup.py
└── hanauta_aipopup/
    ├── app.py                  # DemoWindow, PopupCommandServer, main()
    ├── ui_panel.py             # SidebarPanel (main chat panel)
    ├── ui_chat.py              # ChatWebView, VoiceModeWebView, voice/image/TTS workers
    ├── ui_chat_cards.py        # MessageCard, ComposerBar
    ├── ui_dialogs.py           # CharacterLibraryDialog, VoiceModeDialog
    ├── ui_backend_settings.py  # BackendSettingsDialog (Backends + Skills tabs)
    ├── ui_widgets.py           # Reusable Qt widgets, render_chat_html
    ├── tts.py                  # TTS synthesis, LLM calls, tool-calling loop, emotion injection
    ├── http.py                 # HTTP helpers, backend settings load/save
    ├── storage.py              # Encrypted secrets + chat history (Fernet/SQLite)
    ├── characters.py           # Character card load/save/import
    ├── voice/                  # STT, recording, privacy codebook, stop phrases
    ├── backends/               # KoboldCpp process management
    ├── web/                    # Embedded HTML/CSS/JS for the chat UI
    ├── models.py               # Dataclasses (BackendProfile, ChatItemData, CharacterCard…)
    ├── runtime.py              # Path constants, palette helpers
    └── style.py                # Theme colors, rgba/mix, focused_workspace

skills/
    ├── __init__.py             # Registry: loads skills, runs safety guard on every call
    ├── safety.py               # NSFL guard (BLOCKED + DOUBLE CONFIRM rules)
    ├── py-emotion-engine.py    # Emotion tracking (infer, persist, context injection)
    ├── apprise.py              # Notifications (Telegram, Discord, Slack, ntfy, email…)
    ├── docker.py               # Docker container management
    ├── hanauta-desktop.py      # i3 desktop control (workspaces, windows, wallpaper, lock)
    ├── hanauta-mail.py         # Email read/send (notmuch + msmtp)
    ├── kdeconnect.py           # KDE Connect (ping, SMS, battery, share, ring)
    └── pc-sensors.py           # CPU, RAM, GPU, disk, network, temperature, uptime
```

---

## Tool Calling

Skills are OpenAI-style tool definitions. The LLM picks a tool, the registry executes it, and the result is fed back — up to 4 rounds per message.

**KoboldCpp + Gemma 4** uses native `tool_calls` (requires `--jinja` flag). All other OpenAI-compatible backends use the same native path.

### Safety guard

Every tool call passes through `skills/safety.py` before execution:

| Level | Examples | Behaviour |
|-------|----------|-----------|
| **BLOCKED** | Medical equipment, 911/112 | Refused, no override |
| **DOUBLE CONFIRM** | Garage/gate, door locks, stove, alarms, water valves, circuit breakers | Fullscreen alert shown **twice** using the Hanauta standard alert |

The guard runs in the registry's `call()` — it cannot be bypassed by character personality or prompt injection.

### Emotion engine

`py-emotion-engine.py` infers the user's emotional state from each message (keywords, punctuation, caps ratio) and persists it to `~/.local/state/hanauta/ai-popup/emotion_state.json`. The current emotion is injected into every system prompt so the AI and all skills adapt their tone automatically.

---

## Skills Setup

Open **Backend Settings → Skills tab** to configure each skill:

| Skill | Requires |
|-------|----------|
| **Apprise** | `pip install apprise` + notification URLs (Telegram, Discord, ntfy…) |
| **Docker** | `docker` CLI in PATH |
| **Desktop** | `i3-msg` in PATH |
| **Mail** | `notmuch` (read) + `msmtp` (send) in PATH |
| **KDE Connect** | `kdeconnect-cli` in PATH + paired device |
| **PC Sensors** | `pip install psutil`; GPU needs `nvidia-smi`; temps need `lm-sensors` |
| **Emotion Engine** | No dependencies |

Apprise URL formats: `tgram://bottoken/chatid` · `discord://id/token` · `ntfy://topic` · [full list](https://github.com/caronc/apprise/wiki)

---

## TTS Backends

| Backend | Mode | Notes |
|---------|------|-------|
| KokoroTTS | Local ONNX / External API | Default repo: `onnx-community/Kokoro-82M-ONNX` |
| PocketTTS | Local ONNX / External API | Default repo: `KevinAHM/pocket-tts-onnx` |

Generated audio: `~/.local/state/hanauta/ai-popup/tts-audio/`

Runtime deps for local ONNX:
```
# Kokoro
pip install onnxruntime kokoro-onnx numpy

# PocketTTS
pip install onnxruntime numpy sentencepiece soundfile scipy
```

---

## Voice Mode

Hands-free loop: **record → STT → LLM → TTS → speak → repeat**

Key settings (in Voice Mode settings dialog):

| Key | Description |
|-----|-------------|
| `stt_backend` | `whisper` / `vosk` / `whisperlive` / `llm_audio` / external API |
| `barge_in_enabled` | Interrupt TTS when you start speaking |
| `speech_end_silence_ms` | Silence duration before recording stops (ms) |
| `emotion_tags_enabled` | LLM prefixes replies with `[emotion]` tags |
| `skills_enabled` | Enable tool calling in voice mode |
| `token_saver_enabled` | Compress STT transcripts before sending to LLM |
| `privacy_word_coding_enabled` | Replace sensitive words with tokens before LLM |

---

## Running

```bash
python ai_popup.py
# or with command server (show/hide/toggle from scripts):
python ai_popup.py --server --port 59687
```

Control a running instance:
```bash
python ai_popup.py --command toggle
python ai_popup.py --command show
python ai_popup.py --command hide
```

---

## State Files

All runtime state lives outside the repo in `~/.local/state/hanauta/ai-popup/`:

| File | Contents |
|------|----------|
| `backend_settings.json` | Backend configuration |
| `skills_settings.json` | Per-skill enable flags + Apprise URLs |
| `secure_store.sqlite3` | Encrypted secrets + chat history |
| `secure_store.key` | Fernet encryption key (never commit) |
| `emotion_state.json` | Current emotion state |
| `characters.json` | Character library |
| `tts-audio/` | Generated speech files |
| `voice-recordings/` | Microphone recordings (deleted after STT) |

---

## Character Cards

Import `.json` or `.png` (TavernAI/KoboldCpp format) via the character library dialog.

Template tokens resolved in all character fields:
- `{{char}}` → character name
- `{{user}}` → user's display name (from Hanauta profile)

When a character is active and skills are enabled, the AI offers tool results as:
1. Open the full log in a text viewer
2. Conversational summary
3. Send via a notification channel (if Apprise is configured)

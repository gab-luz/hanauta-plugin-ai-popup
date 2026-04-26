# AGENTS.md — Fast Code Lookup for AI Agents & Contributors

Use this file as the map before touching anything. Every section answers "where does X live?"

---

## Module Map

### Entry points
| File | Role |
|------|------|
| `ai_popup.py` | Thin launcher → `hanauta_aipopup.app:main` |
| `hanauta_plugin.py` | Plugin registration for Hanauta host |

### `hanauta_aipopup/`
| Module | What lives here |
|--------|----------------|
| `app.py` | `DemoWindow`, `PopupCommandServer`, `main()`, diagnostics setup |
| `ui_panel.py` | `SidebarPanel` — the main chat panel, backend pill row, voice controls |
| `ui_chat.py` | `ChatWebView`, `VoiceModeWebView`, `PopupWebBridge`, `SdImageWorker`, `TtsSynthesisWorker`, `VoiceConversationWorker`, `OneShotSttWorker`, `VoiceModelsWarmupWorker` |
| `ui_chat_cards.py` | `MessageCard`, `ComposerBar` |
| `ui_dialogs.py` | `CharacterLibraryDialog`, `VoiceModeDialog` |
| `ui_backend_settings.py` | `BackendSettingsDialog` (Backends tab + Skills tab), `TtsDownloadManager`, `GgufDownloadManager` |
| `ui_widgets.py` | `SurfaceFrame`, `FadeCard`, `ChatInputEdit`, `BackendPill`, `ClickableLineEdit`, `HeaderBadge`, `AntiAliasButton`, `ActionIcon`, `AvatarBadge`, `render_chat_html`, audio helpers |
| `tts.py` | TTS synthesis (Kokoro/Pocket), LLM calls (`_generate_openai_style_reply` with tool-call loop), `generate_voice_chat_reply`, `_chat_messages_for_prompt`, emotion injection, `_load_skills`, server management, systemd |
| `http.py` | HTTP helpers, `load_backend_settings`, `save_backend_settings`, `send_desktop_notification`, `maybe_notify_koboldcpp_release` |
| `storage.py` | Fernet-encrypted secrets + chat history, `_chat_export_payload`, `archive_chat_history` |
| `characters.py` | Character card load/save/import, `_character_compose_prompt`, `_resolve_character_template` |
| `voice/__init__.py` | STT recording, `_voice_mode_defaults`, stop phrases, privacy codebook, `VOICE_EMOTIONS`, `_replace_sensitive_words`, `_extract_emotion_and_clean_text` |
| `backends/__init__.py` | KoboldCpp process management (`start_koboldcpp`, `stop_koboldcpp`, `koboldcpp_status`) |
| `web/` | Embedded HTML/CSS/JS for the chat UI (`popup_html.py`, `popup_css.py`, `popup_js.py`) |
| `models.py` | `BackendProfile`, `ChatItemData`, `CharacterCard`, `SourceChipData` |
| `runtime.py` | Path constants (`AI_STATE_DIR`, `BACKEND_SETTINGS_FILE`, `SKILLS_SETTINGS_FILE`…), `palette_mtime`, `trigger_fullscreen_alert` |
| `style.py` | Theme colors, `rgba()`, `mix()`, `focused_workspace()`, `apply_theme_globals()` |
| `prompt_smartness.py` | `PromptSmartness` — token compression, memory recall, markdown cleanup |
| `catalog.py` | `MODEL_CATALOG`, `_format_bytes`, `_dir_size_bytes` |
| `user_profile.py` | `load_profile_state`, `preferred_user_name` |
| `fonts.py` | `load_ui_font`, `load_material_icon_font`, `button_css_weight` |

### `skills/`
| File | Tools |
|------|-------|
| `__init__.py` | Registry: `tool_definitions()`, `call()` (runs safety guard before every dispatch), `available_names()` |
| `safety.py` | NSFL guard: `safety_check()`, `is_dangerous()`, `SafetyBlocked` |
| `py-emotion-engine.py` | `emotion_get_state`, `emotion_update`, `emotion_history`; `current_emotion()`, `emotion_context_line()`, `infer_emotion()` |
| `apprise.py` | `notify_send`, `notify_list_channels` |
| `docker.py` | `docker_ps`, `docker_start`, `docker_stop`, `docker_restart`, `docker_logs` |
| `hanauta-desktop.py` | `desktop_list_workspaces`, `desktop_switch_workspace`, `desktop_list_windows`, `desktop_focus_window`, `desktop_set_wallpaper`, `desktop_send_notification`, `desktop_run_command`, `desktop_lock_screen` |
| `hanauta-mail.py` | `mail_unread_count`, `mail_list_unread`, `mail_read`, `mail_send`, `mail_search` |
| `kdeconnect.py` | `kdeconnect_list_devices`, `kdeconnect_battery`, `kdeconnect_ping`, `kdeconnect_ring`, `kdeconnect_send_sms`, `kdeconnect_share_file`, `kdeconnect_share_url` |
| `pc-sensors.py` | `sensors_cpu`, `sensors_memory`, `sensors_disk`, `sensors_temperature`, `sensors_gpu`, `sensors_network`, `sensors_uptime`, `sensors_top_processes` |

---

## Key Search Terms

### Tool calling
```
_generate_openai_style_reply   # LLM call + tool_calls loop (tts.py)
_load_skills                   # loads skills registry into tts.py
skills/__init__.py call()      # safety guard + dispatch
safety_check                   # NSFL guard entry point
SafetyBlocked                  # exception raised on blocked actions
_double_confirm                # shows fullscreen alert twice (safety.py)
```

### Emotion engine
```
emotion_context_line()         # one-line context injected into system prompt
infer_emotion()                # text → (emotion, intensity)
emotion_update                 # tool name to update state
emotion_state.json             # persisted state file
```

### Character / {{user}} / {{char}}
```
_resolve_character_template    # replaces {{char}} and {{user}} tokens (tts.py)
_tool_delivery_hint            # injects "offer log or send" hint when character active
_character_compose_prompt      # builds system prompt from CharacterCard fields
CharacterCard                  # dataclass in models.py
```

### Voice mode
```
VoiceConversationWorker        # hands-free loop thread (ui_chat.py)
OneShotSttWorker               # dictation button (ui_chat.py)
_record_until_silence          # end-of-speech detection (voice/__init__.py)
barge_in_enabled               # interrupt TTS on speech
stt_streaming_enabled          # live transcript loop
generate_voice_chat_reply      # full voice reply pipeline (tts.py)
transcribe_voice_audio         # STT dispatch (tts.py)
_select_tts_for_voice          # selects TTS backend for voice mode (ui_panel.py)
selectTtsForVoice             # JS bridge slot (ui_chat.py)
```

### Web bridge slots (PopupWebBridge)
```
bridge.selectBackendAndSay      # /say command TTS picker (ui_chat.py)
bridge.selectTtsForVoice       # voice mode TTS picker (ui_chat.py)
bridge.dismissCard            # remove a card by id (ui_chat.py)
```

### TTS servers
```
_start_kokoro_server / _stop_kokoro_server
_start_pocket_server / _stop_pocket_server
_generate_kokoro_audio_subprocess
_generate_pocket_audio
synthesize_tts                 # main TTS entry point (tts.py)
```

### Backend settings
```
BackendSettingsDialog          # ui_backend_settings.py
_build_skills_tab              # Skills tab builder
_load_skills_settings          # reads skills_settings.json
_save_skills_settings          # writes skills_settings.json
SKILLS_SETTINGS_FILE           # runtime.py path constant
```

### Storage / secrets
```
secure_store_secret / secure_load_secret   # Fernet-encrypted key-value
secure_append_chat / secure_load_chat_history
_chat_export_payload / archive_chat_history
SECURE_DB_FILE / SECURE_KEY_FILE           # runtime.py
```

### Theme / UI
```
apply_theme_globals()          # re-applies Matugen palette to all color constants
palette_mtime()                # mtime of pyqt_palette.json (for live reload)
focused_workspace()            # i3 focused workspace rect (style.py)
render_chat_html()             # builds full chat HTML from history (ui_widgets.py)
--text, --text-mid, --text-dim   # CSS theme color variables (popup_css.py)
--accent                       # CSS accent color variable
```

### Web UI (embedded HTML/CSS/JS)
```
WEB_POPUP_HTML                 # web/popup_html.py
PopupWebBridge                 # Qt ↔ JS bridge (ui_chat.py)
render(payload)                # JS central state render
bridge.*                       # JS → Python calls
stateChanged                   # Python → JS signal
```

---

## Adding a New Skill

1. Create `skills/myskill.py` with `SKILL_DEFINITIONS: list[dict]` and `dispatch(name, args) -> str`
2. Register in `skills/__init__.py` → `_SKILL_FILES` and `_SKILL_ENABLED_KEYS`
3. Add a settings card in `ui_backend_settings.py` → `_build_skills_tab()` if credentials are needed
4. If the skill controls physical hardware, call `safety_check(name, args)` at the top of `dispatch()` — or add a rule to `skills/safety.py`

## Adding a New Backend

1. Add a `BackendProfile` entry in `SidebarPanel.__init__` (`ui_panel.py`)
2. Add backend-specific UI fields in `BackendSettingsDialog.__init__` (`ui_backend_settings.py`)
3. Wire `_load_selected_backend` / `_save_current_backend` / `_test_current_backend`
4. Add launch/stop logic in `backends/__init__.py` if it's a local process

## Changing the System Prompt

Edit `_chat_messages_for_prompt` in `tts.py`. The function builds the system message from:
- Base instruction
- Character prompt (with `{{user}}`/`{{char}}` resolved)
- Tool delivery hint (when character + skills active)
- Live emotion context (from emotion engine)
- Tool definitions (prompt-based fallback, currently unused for KoboldCpp 1.112+)
- Emotion tag suffix

## Minimal Verification

```bash
python3 -m py_compile hanauta_aipopup/app.py hanauta_aipopup/tts.py hanauta_aipopup/ui_backend_settings.py
python3 -c "
import sys; sys.path.insert(0, '.')
for m in ['hanauta_aipopup.tts','hanauta_aipopup.ui_backend_settings','hanauta_aipopup.app']:
    __import__(m); print('OK', m)
import importlib.util
s = importlib.util.spec_from_file_location('skills','skills/__init__.py')
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
print('skills:', len(m.available_names()), 'tools')
"
```

## State Files (never commit)

```
~/.local/state/hanauta/ai-popup/
├── backend_settings.json      # backend config
├── skills_settings.json       # skill enable flags + Apprise URLs
├── secure_store.sqlite3       # encrypted secrets + chat history
├── secure_store.key           # Fernet key  ← NEVER COMMIT
├── emotion_state.json         # current emotion
├── characters.json            # character library
├── tts-audio/                 # generated speech
└── voice-recordings/          # mic recordings (ephemeral)
```

---

## CSS Naming Conventions

Use CSS variables (`var(--text)`, `var(--text-dim)`, `var(--text-mid)`) instead of hardcoded `rgba(255,255,255,...)` for theme-adaptable colors:
- `.body-text strong`, `.body-text b` → `color: var(--text)`
- `.body-text em`, `.body-text i` → `color: var(--text-dim)`
- `.body-text h1-h3` → `color: var(--text)`
- `.chip-pill` → `color: var(--text-dim)`

Avoid hardcoded white/light colors in CSS - always use theme variables.

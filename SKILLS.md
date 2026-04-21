# Hanauta AI Popup: Local "Skills" (for Agents)

This repo does not require any special Codex plumbing, but these conventions speed work up a lot.

## Skill: Find UI Quickly

Goal: locate what to change without reading the whole codebase.

1. HTML UI is in the embedded template: search `WEB_POPUP_HTML`, `.voice-page`, `.chat-page`, `render(payload)`.
2. WebChannel boundary:
   - JS calls: `bridge.*`
   - Python slots/signals: `class PopupWebBridge`, `stateChanged = pyqtSignal(str)`
3. If a UI change doesn't show:
   - confirm `PopupWebView.set_state(...)` includes the field
   - confirm `render(payload)` reads it and updates DOM

Commands:

```bash
rg -n "WEB_POPUP_HTML|render\\(payload\\)|PopupWebBridge|stateChanged" hanauta_aipopup
```

## Skill: Voice Mode Work

Search keys:

- `VoiceConversationWorker`
- `_record_until_silence`
- `stt_streaming_enabled`
- `barge_in_enabled`

Config lives under `_voice_mode` in backend settings storage.

## Skill: Backend Start/Stop

Search keys:

- `_start_koboldcpp` / `_stop_koboldcpp`
- `_start_kokoro_server` / `_stop_kokoro_server`
- `_start_pockettts_server` / `_stop_pockettts_server`
- `startVoiceModels` / `stopVoiceModels`

## Skill: Add New Setting

Checklist:

1. Add default in `_voice_mode_defaults()` (or backend defaults).
2. Add UI control in `VoiceModeSettingsDialog`.
3. Save into the config dict on `accept()`.
4. Read the key where behavior happens (worker / backend launcher).
5. Include it in the state payload if UI needs it.

## Skill: Minimal Verification

```bash
python3 -m py_compile ai_popup.py hanauta_aipopup/full.py
```


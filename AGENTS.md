# Hanauta AI Popup: Agent Notes (Fast Code Lookup)

This plugin is intentionally "web-first UI with Qt glue":

- The **chat + voice mode UI** is HTML/CSS/JS embedded into the app (Qt WebChannel bridge).
- The **backend orchestration** (KoboldCpp, TTS servers, STT venvs, voice loop, logging, persistence) is Python/PyQt6.

If you're an LLM (or a human) trying to change something, use this file as the map.

## Quick Start: Where Things Live

Entry points

- [`ai_popup.py`](/home/gabi/dev/hanauta-plugin-ai-popup/ai_popup.py): tiny launcher (imports `hanauta_aipopup.full:main`).
- [`hanauta_plugin.py`](/home/gabi/dev/hanauta-plugin-ai-popup/hanauta_plugin.py): plugin entry for Hanauta host.
- [`floating_ai_window.py`](/home/gabi/dev/hanauta-plugin-ai-popup/floating_ai_window.py): legacy/alternate popup window (not the web-first one).

Main "app" module (still large, being dismantled)

- [`hanauta_aipopup/full.py`](/home/gabi/dev/hanauta-plugin-ai-popup/hanauta_aipopup/full.py): main window, settings, backends, voice mode loop, web bridge, HTML string.

Supporting modules (already split out)

- [`hanauta_aipopup/style.py`](/home/gabi/dev/hanauta-plugin-ai-popup/hanauta_aipopup/style.py): theme colors, helpers (rgba/mix), CSS-ish constants.
- [`hanauta_aipopup/fonts.py`](/home/gabi/dev/hanauta-plugin-ai-popup/hanauta_aipopup/fonts.py): font loading.
- [`hanauta_aipopup/models.py`](/home/gabi/dev/hanauta-plugin-ai-popup/hanauta_aipopup/models.py): dataclasses / models used across code.
- [`hanauta_aipopup/runtime.py`](/home/gabi/dev/hanauta-plugin-ai-popup/hanauta_aipopup/runtime.py): runtime audio/ears assets, small helpers.
- [`hanauta_aipopup/prompt_smartness.py`](/home/gabi/dev/hanauta-plugin-ai-popup/hanauta_aipopup/prompt_smartness.py): markdown cleanup, prompt tweaks.

## HTML/CSS/JS: The Popup UI

The UI is embedded HTML + CSS + JS (now split into its own module for faster lookup).

Search keys:

- `WEB_POPUP_HTML` (HTML template string, see `hanauta_aipopup/web/popup_html.py`)
- `.voice-page` / `.chat-page` (mode switching)
- `.orb-*` (orb visuals)
- `render(payload)` (central state render)
- `bridge.*` (WebChannel calls into Python)

The Python-side bridge objects:

- `PopupWebBridge` (slots called by JS, signals emitting state updates)
- `PopupWebView.set_state(...)` (sends full state JSON to the HTML UI)

## Voice Mode: Loop + End-of-Speech + Barge-In

Search keys:

- `VoiceConversationWorker` (hands-free loop thread)
- `OneShotSttWorker` (dictation button in chat UI)
- `_record_until_silence` (end-of-speech detection)
- `barge_in_enabled` / `barge_in_threshold`
- `stt_streaming_enabled` (live transcript loop)
- `llm_streaming_enabled` / `tts_streaming_enabled`

End-of-speech tuning settings (config keys):

- `silence_threshold`
- `speech_end_silence_ms`
- `listen_chunk_seconds`
- `min_speech_ms`
- `eos_adaptive_enabled`
- `eos_noise_margin`
- `eos_hysteresis`

## Logs / Terminal Output

Search keys:

- `LOGGER.info` / `LOGGER.warning` / `LOGGER.exception`
- `Voice STT transcript` / `Voice LLM reply` (colored log lines)

Important: avoid writing user chat content into `.log` files. Log files should contain errors/runtime events only.

## Backends + "Start/Stop Loaded"

Search keys:

- `_start_koboldcpp`, `_stop_koboldcpp`
- `_start_kokoro_server`, `_stop_kokoro_server`
- `_start_pockettts_server`, `_stop_pockettts_server`
- `startVoiceModels` / `stopVoiceModels` (bridge calls from HTML)
- `modelsBtn` / `modelsStartBtn` / `modelsStopBtn` (HTML)

## Files Users Edit

- [`curated-model-gallery.json`](/home/gabi/dev/hanauta-plugin-ai-popup/curated-model-gallery.json): curated downloadable model gallery (GGUF now; STT sections reserved).
- [`voice-stop-expressions.json`](/home/gabi/dev/hanauta-plugin-ai-popup/voice-stop-expressions.json): voice stop phrases (pt-BR, en-US, es).
- [`voice-token-compressor.json`](/home/gabi/dev/hanauta-plugin-ai-popup/voice-token-compressor.json): token-saver rules (whisper transcript compression).
- [`voice-privacy-codebook.sample.txt`](/home/gabi/dev/hanauta-plugin-ai-popup/voice-privacy-codebook.sample.txt): sample codebook.

## Fast Command Cheatsheet (Repo Root)

- Find symbol fast: `rg -n "ThingToFind" hanauta_aipopup`
- Python syntax check: `python3 -m py_compile ai_popup.py hanauta_aipopup/full.py`
- Git state: `git status --porcelain=v1`

## Refactor Plan (Ongoing)

Goal: split `hanauta_aipopup/full.py` into smaller modules so agents can load less context:

1. Move the embedded HTML/CSS/JS into `hanauta_aipopup/web/*`.
2. Move voice mode workers + recording helpers into `hanauta_aipopup/voice/*`.
3. Keep `full.py` as a thin composition layer (window wiring + imports).

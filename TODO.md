# TODO (Not Implemented Yet)

This file tracks the remaining work referenced in the last status update:

- Item 2: further modularization / faster code lookup
- Item 5: Whisper as an STT backend (faster-whisper + distill + ONNX + int4)
- Item 6: timestamp-based word highlighting (“karaoke”) in the popup

Date: 2026-04-21

## 2) Further Modularization (Beyond What’s Done)

Already done

- Split embedded web UI into modules:
  - `hanauta_aipopup/web/popup_html.py`
  - `hanauta_aipopup/web/popup_css.py`
  - `hanauta_aipopup/web/popup_js.py`
- Added `AGENTS.md` and `SKILLS.md`.
- Moved curated model catalog loader utilities into `hanauta_aipopup/catalog.py`.

Still to do

1. Split `hanauta_aipopup/full.py` into focused modules:
   - `hanauta_aipopup/voice/`:
     - recording helpers (`_record_microphone_wav`, `_wav_duration_seconds`, RMS helpers)
     - end-of-speech logic (incl adaptive/hysteresis)
     - `VoiceConversationWorker`, `OneShotSttWorker`, `VoiceModelsWarmupWorker`
   - `hanauta_aipopup/backends/`:
     - KoboldCpp process management
     - Kokoro/Pocket server management
     - OpenAI-compatible HTTP helpers / errors
   - `hanauta_aipopup/ui/qt/`:
     - `DemoWindow`, `SidebarPanel`
     - settings dialogs (Voice Mode settings, backend settings, character library dialogs)
   - `hanauta_aipopup/ui/web/`:
     - state payload schema helpers (`build_state_payload(...)`)
     - WebChannel bridge (`PopupWebBridge`)

2. Keep `full.py` as composition glue:
   - imports modules
   - wires signals/slots
   - exposes `main()`

3. Reduce agent “search cost”:
   - update `AGENTS.md` with the new module map and “search keys”
   - keep public entry points stable (`ai_popup.py` -> `hanauta_aipopup.full:main`)

## 5) Whisper as a Backend in Backend Settings (STT)

Goal

- Treat STT as a first-class backend in the backend settings UI (not only Voice Mode settings).
- Support multiple engine flavors:
  - faster-whisper (CTranslate2) local
  - distil-whisper variants (where compatible)
  - ONNX whisper (onnxruntime) with quantized options (int4) for:
    - `onnx-community/whisper-medium.en_timestamped`

Missing pieces

1. Backend settings UI
   - Add a dedicated “STT: Whisper” backend panel alongside existing backends.
   - Allow selecting:
     - engine: `faster-whisper` vs `onnx-whisper`
     - model family: standard / distill / optimized
     - model id/path
     - device: CPU/GPU
     - external API toggle (OpenAI Whisper / compatible) per STT backend

2. Curated model gallery integration for STT
   - Replace hardcoded STT model suggestions with curated entries from:
     - `curated-model-gallery.json` sections:
       - `stt_whisper`
       - `stt_whisper_distill`
       - `stt_whisper_onnx`
   - UI should show model metadata (size, language, notes, license, “recommended for CPU”, etc).
   - Download flow:
     - for HF models: download to a managed cache directory
     - show progress, final size, and “ready” state

3. Execution backends
   - faster-whisper:
     - already used for one-shot and (best-effort) streaming; needs refactor into a reusable STT backend object
     - ensure per-model per-device isolated venv is used (already a repo convention)
   - ONNX whisper:
     - add a new isolated venv type for ONNX STT deps (onnxruntime CPU/GPU variants)
     - implement model download/caching:
       - fetch model + tokenizer assets
     - implement transcription call that returns:
       - plain text
       - timestamps data (at least segment timestamps; ideally word timestamps)
   - int4 quant support:
     - confirm which onnxruntime build and model format the HF int4 files need
     - add “int4” option in curated gallery metadata and in the backend settings UI

4. Voice Mode plumbing
   - Voice mode must be able to select STT backend from backend settings, not only voice-mode settings.
   - Make sure it’s consistent:
     - STT backend “loaded/unloaded” states reflect in the UI
     - model sizes/info show up in the info tooltip and model launcher sheet

## 6) Timestamp-Based Word Highlighting (“Karaoke”)

Goal

- While the user is speaking (or while a transcript is being streamed), highlight the currently spoken word.
- If the STT backend provides timestamps, use them to drive highlighting.

Current state

- Only a “best-effort last word highlight” exists in Voice Mode transcript UI (not timestamp-accurate).

Missing pieces

1. Decide the timestamp granularity available
   - faster-whisper:
     - implement `word_timestamps` (if available in the chosen faster-whisper version) or segment-level fallback
   - ONNX timestamped model:
     - confirm whether it provides per-word times or only segment times
     - define a normalized output:
       - `[{word, start_ms, end_ms}, ...]` preferred
       - else `[{segment_text, start_ms, end_ms}, ...]`

2. Transport timestamps to the web UI
   - Extend voice state payload with (optional) timing data:
     - `voice.transcript_words: [{t, s, e}]` or similar
     - a `voice.clock_ms` or `voice.capture_started_ms` reference so JS can compute “now”
   - Keep payload small (cap words list length, or only ship the active window + upcoming words).

3. Drive highlighting in JS
   - On each state update (or a small JS timer), compute which word index is active based on elapsed time.
   - Render transcript as:
     - non-highlighted words
     - one active highlighted word
     - optionally “spoken” words styled differently

4. Sync concerns
   - For streamed STT: capture start time needs to be stable; chunk boundaries add drift.
   - For one-shot STT: only post-hoc highlight is possible (still useful for review, but not “live”).
   - For live karaoke: prefer a STT backend that emits incremental words with timestamps, or use VAD + incremental decoding.

5. UX knobs
   - setting: enable/disable karaoke highlighting
   - setting: highlight style (subtle vs strong)
   - fallback: if timestamps missing, fall back to last-word highlight (current behavior)


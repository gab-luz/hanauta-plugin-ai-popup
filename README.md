# hanauta-plugin-ai-popup

Hanauta plugin repository for ai popup.

## Entrypoints
- hanauta_plugin.py (plugin metadata/registration when present)

## Usage
Install through Hanauta Marketplace or clone into your Hanauta plugins directory.

## TTS backends (Kokoro ONNX + PocketTTS ONNX)
- `KokoroTTS` and `PocketTTS` now support:
  - `Local ONNX` mode (model files on disk, optional auto-download from Hugging Face)
  - `External API` mode (custom URL, optional API key)
- In backend settings:
  - choose backend (`KokoroTTS` or `PocketTTS`)
  - choose `Local ONNX` or `External API`
  - for local mode, either set a local model folder or click `Download TTS model`
  - while downloading, a progress bar is shown in settings; closing the dialog does not stop the download
  - for Kokoro downloads, completion triggers a fullscreen Hanauta reminder with a `Start Kokoro Server` button
  - for external mode, set host URL and API key if required

### Local ONNX notes
- Kokoro default model repo: `onnx-community/Kokoro-82M-ONNX`
- PocketTTS ONNX default repo: `KevinAHM/pocket-tts-onnx` (community ONNX export for Kyutai PocketTTS)
- PocketTTS optional local server:
  - this repo ships a small local server wrapper under `onnx/cpp/pockettts_server/`
  - it exposes an OpenAI-compatible `POST /v1/audio/speech` endpoint and calls the existing PocketTTS ONNX Python module
  - it is **not** used by default; install it from the PocketTTS backend settings (button) and start it explicitly
  - `language` is supported as an optional field in the request JSON (passed through to the Python engine when supported)
- Optional fallback for CDN/timeout issues:
  - set `TTS bundle URL` to a ZIP release asset URL
  - downloader will fetch and extract the ZIP into the model folder, then validate required files
- Generated audio is written to:
  - `~/.local/state/hanauta/ai-popup/tts-audio`

### Runtime dependencies for local ONNX
Install into the Python environment used by the plugin:
- Kokoro local mode:
  - `onnxruntime`
  - `kokoro-onnx`
  - `numpy`
- Pocket local mode:
  - `onnxruntime`
  - `numpy`
  - `sentencepiece`
  - `soundfile`
  - `scipy`

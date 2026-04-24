# TODO (Not Implemented Yet)

This file tracks the remaining work referenced in the last status update:

- Item 2: further modularization / faster code lookup
- Item 5: Whisper as an STT backend (faster-whisper + distill + ONNX + int4)
- Item 6: timestamp-based word highlighting (“karaoke”) in the popup
- Item 7: utility APIs (translation, search, weather)

Date: 2026-04-23

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

## 7) Utility APIs (Translation / Search / Weather / Integrations)

Goal

- Add optional, privacy-conscious “tool” style APIs the popup can call for:
  - translations
  - web search
  - weather
- Keep these as independent modules with a shared, minimal result schema so they can be used by:
  - chat actions (e.g. “Translate selection”, “Search”, “Weather”)
  - voice mode “tool intent” (later)
  - prompt augmentation (optional, user-controlled)

Missing pieces

1. Shared API client base
   - Add a small HTTP helper with:
     - timeouts (short, e.g. 5–10s)
     - retries (limited)
     - JSON decode errors surfaced cleanly to the UI
     - optional disk/memory cache for “safe to cache” requests
   - Add settings for:
     - per-provider enable/disable
     - base URLs and API keys (when required)
     - “never send chat history” guardrails (only send user-selected text / short query strings)

2. Translation: `translate.disroot.org` (LibreTranslate-compatible)
   - Implement a `TranslationClient`:
     - detect language (optional)
     - translate text (`source`, `target`)
     - list languages (cache)
   - Also support user-configured self-hosted LibreTranslate base URLs (same client).
   - UI wiring:
     - quick action: translate selected text (paste result back into the chat input)
     - quick action: translate last assistant/user message (opt-in)
   - Settings:
     - default source: `auto`
     - default target language (e.g. `en`, `pt`, etc.)
     - max text length (prevent accidental huge payloads)

3. Search: Brave Search API OR SearXNG JSON API
   - Define a shared result schema:
     - `[{title, url, snippet, source, published_at?}]`
   - Implement providers:
     - `BraveSearchClient` (API key required)
     - `SearxngClient` (self-host / public instance base URL)
   - UI wiring:
     - quick action: “Search the web” from a short query
     - render results in the chat as a compact list (clickable links)
     - optional “summarize results” prompt (explicit user action)
   - Settings:
     - default engine: `brave` | `searxng`
     - safe search toggle (where supported)
     - results limit

4. Weather: Open-Meteo API
   - Implement `OpenMeteoClient`:
     - geocoding query -> lat/lon (Open-Meteo geocoding)
     - forecast endpoint(s) for current + daily/hourly as needed
     - timezone/unit selection (user-configurable)
   - Meteostat (historical weather / climate stats):
     - station search near a location (or by ID)
     - daily/hourly history endpoints for charts and “what was it like last week?”
   - UI wiring:
     - quick action: “Weather” with location input (city string)
     - paste a short human-readable forecast into chat (not raw JSON)
   - Caching:
     - cache geocoding results and short-term forecasts for a few minutes

5. Knowledge lookups (encyclopedia + dictionary)
   - Wikipedia / MediaWiki REST:
     - page summary / extract
     - “quick facts” (best-effort via pageprops / infobox parsing if needed later)
   - Wiktionary / dictionary:
     - definitions + examples
     - pronunciation (IPA string; audio later if available)
   - UI wiring:
     - quick action: “Lookup” from a short query
     - paste a compact “card” into chat (title + bullets + source link)

6. Math / conversions / rates
   - Currency exchange rates:
     - provider: Frankfurter API (free) as the default
     - conversions: `10 USD -> BRL` with cached daily rates
   - Unit conversion:
     - start as local-only conversion tables (preferred), with an optional API later
   - WolframAlpha:
     - optional advanced queries (API key)
     - ensure “show source link” + “don’t send chat history” guardrails

7. Dev + research search APIs
   - GitHub API:
     - repo search
     - issues/PR search
     - minimal auth token storage + scopes guidance
   - arXiv:
     - paper search + metadata (title/authors/abstract/pdf link)
   - Semantic Scholar:
     - paper search + citations (API key optional depending on limits)

8. Places + network identity
   - OpenStreetMap:
     - Nominatim/Photon for places search / richer geocoding
   - IP / ASN lookup:
     - provider: ipinfo (API key)
     - show: ISP/ASN/city/country (no background tracking; explicit user action only)

9. Feeds + monitoring
   - RSS/Atom fetch + parse:
     - “headlines” cards (title/link/date/source)
     - per-feed refresh interval + caching
   - “Check page for changes”:
     - store URL + selector/text-extract rule
     - scheduled fetch + diff
     - notify via the popup (and/or Hanauta notifications) when changed

10. Local helpers (no network required)
   - OCR (Tesseract):
     - quick action: OCR clipboard image / screenshot -> paste text
   - Language detection (fastText local model):
     - detect language code for pasted/selected text (used by translation defaults)
   - QR generate/decode:
     - tools: `qrencode` + `zbarimg`
     - quick actions: “Create QR from text” and “Decode QR from image”
   - Clipboard manager integration:
     - quick actions: “pin snippet”, “clear sensitive clipboard”

11. Personal + home integrations (explicitly opt-in)
   - Email send (SMTP):
     - compose -> confirm -> send
     - store creds securely (or use app password)
   - CalDAV (Nextcloud):
     - create TODO (VTODO) / list TODOs
   - Nextcloud:
     - Deck: list boards/cards, create card
     - Files: upload/download/share links (explicit confirmation)
   - Joplin Web Clipper API:
     - save snippet/summary as a note (tags + notebook)
   - Home Assistant:
     - read sensors + run service (confirm before actuation)
   - Grocy:
     - server base URL + API key (user-provided)
     - inventory overview (low stock / expiring soon)
     - add to shopping list / consume product / adjust stock
     - optional barcode lookup flow (pair with Open Food Facts)
     - daily/weekly digest card in the popup (e.g. “expiring soon”)
   - Jellyfin:
     - server base URL + API key (user-provided)
     - “Now playing”, recently added, and basic playback control (if enabled)
   - Uptime Kuma:
     - list monitors + show status + last incident

12. Package search (Linux distros)
   - Debian/Ubuntu:
     - package search + version + homepage
   - Arch:
     - official repos + AUR search (split results clearly)

13. Time utilities
   - Timezone / world clock:
     - “convert 3pm PST to my time”
     - show local + target time with explicit date when ambiguous

14. Price tracking (opt-in)
   - Track a URL + parse rule (or site-specific adapters later)
   - Scheduled checks + change notifications

15. Product lookup (free)
   - Open Food Facts:
     - barcode lookup -> nutrition/ingredients/allergens
     - text search -> top matches
     - render a compact product card (name/brand + key fields + source link)

16. More free/local integrations
   - Transit (GTFS, free data):
     - ingest a local/URL GTFS feed (static) and show next departures for a stop
   - Music metadata:
     - MusicBrainz lookup (artist/album/track)
     - Cover Art Archive for album art URLs
   - Podcasts:
     - iTunes Search API (free) for show search + basic metadata
     - (optional) PodcastIndex support later if you decide keys are acceptable
   - Movie/TV metadata:
     - TVmaze API (free) for show search, episode lists, schedules
   - Recipes:
     - TheMealDB (free tier) for recipe search + details
   - Local speed test:
     - wrap `speedtest-cli` (or equivalent) and render a “network snapshot” card
   - Local system “health snapshot”:
     - wrap `smartctl` / `lsblk` / `sensors` into a compact status card

17. More free APIs (no keys)
   - Wikidata:
     - SPARQL query runner + a few curated query templates (facts, relationships, “top properties”)
   - OpenAlex:
     - research discovery (works/authors/institutions/topics) + short “paper card” rendering
   - Crossref:
     - DOI lookup + citation metadata cards
   - Open Library:
     - ISBN/author/title lookup + edition metadata
   - Project Gutenberg:
     - catalog search + download links (metadata-only in the UI; downloads optional)
   - Stack Exchange:
     - StackOverflow/SE search + “top answers” preview cards (respect rate limits)
   - Hacker News search:
     - Algolia HN API for stories/comments search + “trending” shortcuts
   - REST Countries:
     - country lookup cards (capital, currencies, languages, calling code)
   - Public holidays:
     - Nager.Date for holiday lists + “next holiday” helper
   - Earthquake status:
     - USGS earthquakes feed for “recent near X” + magnitude/time cards
   - OSM Overpass API:
     - POI/amenity lookup near a location (cafes, pharmacies, etc.), cached + rate-limited
   - GDELT:
     - global news/search snapshots (simple query -> headlines list)
   - Jikan (MyAnimeList community API):
     - anime/manga lookup + episode/season info cards
   - CoinGecko:
     - crypto price + simple watchlist cards (rate-limited, cached)

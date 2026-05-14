# Locale Files

This plugin loads UI translations from JSON files in this folder.

## Supported defaults

- `pt-BR.json`
- `en-US.json`
- `es-419.json` (Latin American Spanish)
- `ru-RU.json`

## Format (translation-platform friendly)

Each file is UTF-8 JSON with a `strings` object of key/value pairs.

```json
{
  "meta": {
    "locale": "en-US",
    "name": "English (US)"
  },
  "strings": {
    "plugin.ai_popup.name": "AI Popup"
  }
}
```

This structure works well with common online translation platforms (Weblate, Crowdin, Lokalise, POEditor) that support JSON key-value resources.

## Locale detection

Runtime locale is auto-detected from:

1. `HANAUTA_AI_POPUP_LOCALE`
2. `LC_ALL`
3. `LANG`
4. `LANGUAGE`

Fallback is always `en-US`.


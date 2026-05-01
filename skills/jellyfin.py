"""
Jellyfin skill — control playback, browse library, search, and manage sessions.

Credentials stored in skills_settings.json under "jellyfin":
    {
        "jellyfin": {
            "enabled": true,
            "url": "http://jellyfin.local:8096",
            "api_key": "<API key from Dashboard → API Keys>"
        }
    }

API key: Jellyfin Dashboard → Administration → API Keys → + (New Key).
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib import error, request
from urllib.parse import quote

_SETTINGS_FILE = (
    Path.home() / ".local" / "state" / "hanauta" / "ai-popup" / "skills_settings.json"
)

SKILL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "jellyfin_now_playing",
            "description": "Show what is currently playing on all Jellyfin sessions.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "jellyfin_search",
            "description": "Search the Jellyfin library for movies, series, episodes, music, or any media.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search term."},
                    "media_type": {
                        "type": "string",
                        "description": "Optional filter: 'Movie', 'Series', 'Episode', 'Audio', 'MusicAlbum', 'MusicArtist'. Leave empty for all.",
                    },
                    "limit": {"type": "integer", "description": "Max results (default 8)."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "jellyfin_recently_added",
            "description": "List recently added items in the Jellyfin library.",
            "parameters": {
                "type": "object",
                "properties": {
                    "media_type": {
                        "type": "string",
                        "description": "Optional filter: 'Movie', 'Series', 'Audio'. Leave empty for all.",
                    },
                    "limit": {"type": "integer", "description": "Max results (default 10)."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "jellyfin_play",
            "description": "Start playing a media item on a Jellyfin session/device.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string", "description": "Jellyfin item ID to play."},
                    "session_id": {
                        "type": "string",
                        "description": "Session ID to play on. Leave empty to use the first active session.",
                    },
                },
                "required": ["item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "jellyfin_pause",
            "description": "Pause playback on a Jellyfin session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID. Leave empty to pause the first active session.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "jellyfin_resume",
            "description": "Resume playback on a Jellyfin session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID. Leave empty for first active session."}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "jellyfin_stop",
            "description": "Stop playback on a Jellyfin session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID. Leave empty for first active session."}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "jellyfin_next",
            "description": "Skip to the next item in the queue on a Jellyfin session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID. Leave empty for first active session."}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "jellyfin_set_volume",
            "description": "Set the volume on a Jellyfin session (0–100).",
            "parameters": {
                "type": "object",
                "properties": {
                    "volume": {"type": "integer", "description": "Volume level 0–100."},
                    "session_id": {"type": "string", "description": "Session ID. Leave empty for first active session."},
                },
                "required": ["volume"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "jellyfin_list_sessions",
            "description": "List all active Jellyfin sessions and their playback state.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "jellyfin_item_info",
            "description": "Get detailed info about a Jellyfin media item by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string", "description": "Jellyfin item ID."}
                },
                "required": ["item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "jellyfin_next_up",
            "description": "Show the next up episodes for series the user is watching.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max results (default 8)."}
                },
                "required": [],
            },
        },
    },
]


# ── Config ────────────────────────────────────────────────────────────────────

def _load_cfg() -> dict:
    try:
        cfg = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8")).get("jellyfin", {})
    except Exception:
        cfg = {}
    if not cfg.get("api_key"):
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from hanauta_aipopup.storage import secure_load_secret
            key = secure_load_secret("skills:jellyfin:api_key")
            if key:
                cfg = dict(cfg)
                cfg["api_key"] = key
        except Exception:
            pass
    return cfg


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _api(cfg: dict, path: str, method: str = "GET",
         body: dict | None = None, params: dict | None = None) -> object:
    url = str(cfg.get("url", "")).rstrip("/")
    api_key = str(cfg.get("api_key", "")).strip()
    if not url:
        raise RuntimeError(
            "Jellyfin URL not configured. Set it in Backend Settings → Skills → Jellyfin."
        )
    if not api_key:
        raise RuntimeError(
            "Jellyfin API key not configured. Set it in Backend Settings → Skills → Jellyfin."
        )
    query = f"api_key={api_key}"
    if params:
        for k, v in params.items():
            query += f"&{k}={quote(str(v))}"
    full_url = f"{url}{path}?{query}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    req = request.Request(full_url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=10.0) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            return json.loads(raw) if raw.strip() else {}
    except error.HTTPError as exc:
        raise RuntimeError(f"Jellyfin API error {exc.code}: {exc.read().decode('utf-8', errors='ignore')[:200]}")
    except Exception as exc:
        raise RuntimeError(f"Jellyfin connection failed: {exc}")


def _post(cfg: dict, path: str, body: dict | None = None) -> None:
    """Fire-and-forget POST (playback commands return 204)."""
    url = str(cfg.get("url", "")).rstrip("/")
    api_key = str(cfg.get("api_key", "")).strip()
    full_url = f"{url}{path}?api_key={api_key}"
    headers = {"Content-Type": "application/json"}
    data = json.dumps(body or {}).encode()
    req = request.Request(full_url, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=8.0):
            pass
    except error.HTTPError as exc:
        if exc.code not in (200, 204):
            raise RuntimeError(f"Jellyfin POST error {exc.code}")
    except Exception as exc:
        raise RuntimeError(f"Jellyfin connection failed: {exc}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_item(item: dict) -> str:
    name = item.get("Name", "?")
    itype = item.get("Type", "")
    year = item.get("ProductionYear", "")
    series = item.get("SeriesName", "")
    season = item.get("ParentIndexNumber", "")
    episode = item.get("IndexNumber", "")
    item_id = item.get("Id", "")

    label = name
    if itype == "Episode" and series:
        label = f"{series} S{season:02d}E{episode:02d} — {name}" if season and episode else f"{series} — {name}"
    elif year:
        label = f"{name} ({year})"

    return f"[{itype}] {label}  (id: {item_id})"


def _fmt_duration(ticks: int | None) -> str:
    if not ticks:
        return ""
    seconds = int(ticks / 10_000_000)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _first_active_session(sessions: list) -> dict | None:
    playing = [s for s in sessions if s.get("NowPlayingItem")]
    if playing:
        return playing[0]
    return sessions[0] if sessions else None


def _resolve_session(cfg: dict, session_id: str) -> str:
    if session_id.strip():
        return session_id.strip()
    sessions = _api(cfg, "/Sessions")
    if not isinstance(sessions, list) or not sessions:
        raise RuntimeError("No active Jellyfin sessions found.")
    s = _first_active_session(sessions)
    if s is None:
        raise RuntimeError("No active Jellyfin sessions found.")
    return str(s.get("Id", ""))


# ── Dispatch ──────────────────────────────────────────────────────────────────

def dispatch(name: str, args: dict) -> str:
    cfg = _load_cfg()
    if not bool(cfg.get("enabled", True)):
        return "[jellyfin] Skill is disabled in settings."

    try:
        if name == "jellyfin_now_playing":
            sessions = _api(cfg, "/Sessions")
            if not isinstance(sessions, list):
                return "No sessions found."
            playing = [s for s in sessions if s.get("NowPlayingItem")]
            if not playing:
                return "Nothing is currently playing on Jellyfin."
            lines = []
            for s in playing:
                item = s.get("NowPlayingItem", {})
                client = s.get("Client", "?")
                device = s.get("DeviceName", "?")
                pos = s.get("PlayState", {}).get("PositionTicks")
                dur = item.get("RunTimeTicks")
                progress = f"{_fmt_duration(pos)} / {_fmt_duration(dur)}" if pos and dur else ""
                lines.append(
                    f"▶ {item.get('Name', '?')} — {client} on {device}"
                    + (f"  [{progress}]" if progress else "")
                )
            return "\n".join(lines)

        if name == "jellyfin_search":
            query = str(args.get("query", "")).strip()
            media_type = str(args.get("media_type", "")).strip()
            limit = int(args.get("limit") or 8)
            params: dict = {"searchTerm": query, "Limit": str(limit), "Recursive": "true"}
            if media_type:
                params["IncludeItemTypes"] = media_type
            result = _api(cfg, "/Items", params=params)
            items = result.get("Items", []) if isinstance(result, dict) else []
            if not items:
                return f"No results for '{query}'."
            return "\n".join(_fmt_item(i) for i in items)

        if name == "jellyfin_recently_added":
            media_type = str(args.get("media_type", "")).strip()
            limit = int(args.get("limit") or 10)
            params: dict = {"Limit": str(limit), "SortBy": "DateCreated", "SortOrder": "Descending", "Recursive": "true"}
            if media_type:
                params["IncludeItemTypes"] = media_type
            result = _api(cfg, "/Items", params=params)
            items = result.get("Items", []) if isinstance(result, dict) else []
            if not items:
                return "No recently added items found."
            return "Recently added:\n" + "\n".join(_fmt_item(i) for i in items)

        if name == "jellyfin_play":
            item_id = str(args.get("item_id", "")).strip()
            session_id = _resolve_session(cfg, str(args.get("session_id", "")))
            _post(cfg, f"/Sessions/{session_id}/Playing",
                  {"PlayCommand": "PlayNow", "ItemIds": [item_id]})
            return f"Playing item {item_id} on session {session_id}."

        if name == "jellyfin_pause":
            session_id = _resolve_session(cfg, str(args.get("session_id", "")))
            _post(cfg, f"/Sessions/{session_id}/Playing/Unpause"
                  if False else f"/Sessions/{session_id}/Playing/Pause")
            return f"Paused session {session_id}."

        if name == "jellyfin_resume":
            session_id = _resolve_session(cfg, str(args.get("session_id", "")))
            _post(cfg, f"/Sessions/{session_id}/Playing/Unpause")
            return f"Resumed session {session_id}."

        if name == "jellyfin_stop":
            session_id = _resolve_session(cfg, str(args.get("session_id", "")))
            _post(cfg, f"/Sessions/{session_id}/Playing/Stop")
            return f"Stopped session {session_id}."

        if name == "jellyfin_next":
            session_id = _resolve_session(cfg, str(args.get("session_id", "")))
            _post(cfg, f"/Sessions/{session_id}/Playing/NextItem")
            return f"Skipped to next item on session {session_id}."

        if name == "jellyfin_set_volume":
            volume = max(0, min(100, int(args.get("volume", 50))))
            session_id = _resolve_session(cfg, str(args.get("session_id", "")))
            _post(cfg, f"/Sessions/{session_id}/Message",
                  {"Header": "Volume", "Text": str(volume)})
            # Also try the GeneralCommand approach
            try:
                _post(cfg, f"/Sessions/{session_id}/Command",
                      {"Name": "SetVolume", "Arguments": {"Volume": str(volume)}})
            except Exception:
                pass
            return f"Volume set to {volume}% on session {session_id}."

        if name == "jellyfin_list_sessions":
            sessions = _api(cfg, "/Sessions")
            if not isinstance(sessions, list) or not sessions:
                return "No active Jellyfin sessions."
            lines = []
            for s in sessions:
                client = s.get("Client", "?")
                device = s.get("DeviceName", "?")
                user = s.get("UserName", "?")
                sid = s.get("Id", "?")
                item = s.get("NowPlayingItem")
                state = f"▶ {item['Name']}" if item else "idle"
                lines.append(f"[{sid[:8]}…] {user} — {client} on {device}: {state}")
            return "\n".join(lines)

        if name == "jellyfin_item_info":
            item_id = str(args.get("item_id", "")).strip()
            item = _api(cfg, f"/Items/{item_id}")
            if not isinstance(item, dict):
                return f"Item {item_id} not found."
            lines = [
                f"Name: {item.get('Name', '?')}",
                f"Type: {item.get('Type', '?')}",
                f"Year: {item.get('ProductionYear', '?')}",
                f"Duration: {_fmt_duration(item.get('RunTimeTicks'))}",
                f"Rating: {item.get('OfficialRating', '?')}",
                f"Community score: {item.get('CommunityRating', '?')}",
            ]
            overview = str(item.get("Overview", "")).strip()
            if overview:
                lines.append(f"Overview: {overview[:300]}{'…' if len(overview) > 300 else ''}")
            genres = item.get("Genres", [])
            if genres:
                lines.append(f"Genres: {', '.join(genres)}")
            return "\n".join(lines)

        if name == "jellyfin_next_up":
            limit = int(args.get("limit") or 8)
            result = _api(cfg, "/Shows/NextUp", params={"Limit": str(limit)})
            items = result.get("Items", []) if isinstance(result, dict) else []
            if not items:
                return "No next-up episodes found."
            return "Next up:\n" + "\n".join(_fmt_item(i) for i in items)

    except Exception as exc:
        return f"[jellyfin] {exc}"

    return f"[jellyfin] unknown tool: {name}"

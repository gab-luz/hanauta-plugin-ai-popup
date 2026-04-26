"""
Calendar skill — read and create events via CalDAV or local ICS files.

Supports:
  - CalDAV servers: Nextcloud, Radicale, Baikal, Google Calendar, iCloud
  - Local ICS files (read-only)

Credentials stored in skills_settings.json under "calendar":
    {
        "calendar": {
            "enabled": true,
            "backend": "caldav",          # "caldav" or "ics"
            "url": "https://nextcloud.example.com/remote.php/dav/calendars/user/",
            "username": "user",
            "ics_path": "/home/user/calendar.ics"
        }
    }
Password stored encrypted via secure_store_secret("skills:calendar:password").
"""
from __future__ import annotations

import json
import locale
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import error, request
from urllib.parse import urljoin

_SETTINGS_FILE = (
    Path.home() / ".local" / "state" / "hanauta" / "ai-popup" / "skills_settings.json"
)


# ── Locale-aware date formatting ──────────────────────────────────────────────

def _system_locale() -> str:
    """Return the system locale code, e.g. 'pt_BR.UTF-8'."""
    for var in ("LANG", "LANGUAGE", "LC_TIME", "LC_ALL"):
        val = os.environ.get(var, "").split(":")[0].strip()
        if val and val != "C" and val != "POSIX":
            return val
    try:
        return locale.getlocale()[0] or "en_US"
    except Exception:
        return "en_US"


def _fmt_dt(dt: datetime, all_day: bool) -> str:
    """
    Format a datetime using the system locale so day/month names appear
    in the user's language (e.g. 'Seg 25 Abr 14:30' for pt_BR).
    """
    sys_locale = _system_locale()
    # Try to set locale temporarily for strftime
    candidates = [sys_locale, sys_locale.split(".")[0] + ".UTF-8",
                  sys_locale.split("_")[0] + "_" + sys_locale.split("_")[-1].split(".")[0] + ".UTF-8"]
    saved = locale.getlocale(locale.LC_TIME)
    for loc in candidates:
        try:
            locale.setlocale(locale.LC_TIME, loc)
            fmt = "%a %d %b" if all_day else "%a %d %b %H:%M"
            result = dt.strftime(fmt)
            locale.setlocale(locale.LC_TIME, saved)
            return result
        except locale.Error:
            continue
    locale.setlocale(locale.LC_TIME, saved)
    # Fallback: plain ISO
    return dt.strftime("%Y-%m-%d") if all_day else dt.strftime("%Y-%m-%d %H:%M")


def _locale_label(key: str) -> str:
    """
    Return locale-aware UI strings for common calendar labels.
    Covers pt_BR, es, fr, de, it, ja, zh; falls back to English.
    """
    lang = _system_locale().split("_")[0].lower().split(".")[0]
    labels: dict[str, dict[str, str]] = {
        "today": {
            "pt": "Hoje", "es": "Hoy", "fr": "Aujourd'hui", "de": "Heute",
            "it": "Oggi", "ja": "今日", "zh": "今天", "nl": "Vandaag",
            "pl": "Dzisiaj", "ru": "Сегодня",
        },
        "this_week": {
            "pt": "Esta semana", "es": "Esta semana", "fr": "Cette semaine",
            "de": "Diese Woche", "it": "Questa settimana", "ja": "今週",
            "zh": "本周", "nl": "Deze week", "pl": "Ten tydzień", "ru": "На этой неделе",
        },
        "no_events_today": {
            "pt": "Nenhum evento hoje.", "es": "Sin eventos hoy.",
            "fr": "Aucun événement aujourd'hui.", "de": "Keine Ereignisse heute.",
            "it": "Nessun evento oggi.", "ja": "今日のイベントはありません。",
            "zh": "今天没有活动。", "nl": "Geen evenementen vandaag.",
        },
        "no_events_week": {
            "pt": "Nenhum evento esta semana.", "es": "Sin eventos esta semana.",
            "fr": "Aucun événement cette semaine.", "de": "Keine Ereignisse diese Woche.",
            "it": "Nessun evento questa settimana.",
        },
        "no_events": {
            "pt": "Nenhum evento encontrado.", "es": "Sin eventos.",
            "fr": "Aucun événement.", "de": "Keine Ereignisse.",
            "it": "Nessun evento.",
        },
        "calendars": {
            "pt": "Calendários", "es": "Calendarios", "fr": "Calendriers",
            "de": "Kalender", "it": "Calendari",
        },
        "event_created": {
            "pt": "Evento criado", "es": "Evento creado", "fr": "Événement créé",
            "de": "Ereignis erstellt", "it": "Evento creato",
        },
        "at": {
            "pt": "em", "es": "en", "fr": "à", "de": "in", "it": "a",
        },
        "matching": {
            "pt": "Eventos com", "es": "Eventos con", "fr": "Événements avec",
            "de": "Ereignisse mit", "it": "Eventi con",
        },
        "no_matching": {
            "pt": "Nenhum evento encontrado para", "es": "Sin eventos para",
            "fr": "Aucun événement pour", "de": "Keine Ereignisse für",
            "it": "Nessun evento per",
        },
    }
    return labels.get(key, {}).get(lang, {
        "today": "Today", "this_week": "This week",
        "no_events_today": "No events today.",
        "no_events_week": "No events this week.",
        "no_events": "No events found.",
        "calendars": "Calendars",
        "event_created": "Event created",
        "at": "at", "matching": "Events matching",
        "no_matching": "No events matching",
    }.get(key, key))

SKILL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "calendar_list_events",
            "description": "List upcoming calendar events within a time range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {
                        "type": "integer",
                        "description": "How many days ahead to look (default 7, max 90).",
                    },
                    "days_back": {
                        "type": "integer",
                        "description": "How many days back to include (default 0).",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max events to return (default 20).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_get_today",
            "description": "Get all events happening today.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_get_week",
            "description": "Get all events for the current week (Mon–Sun).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_create_event",
            "description": "Create a new calendar event.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Event title/summary."},
                    "start": {
                        "type": "string",
                        "description": "Start datetime in ISO 8601 format, e.g. '2025-06-15T14:00:00' or '2025-06-15' for all-day.",
                    },
                    "end": {
                        "type": "string",
                        "description": "End datetime in ISO 8601 format. Defaults to 1 hour after start.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional event description/notes.",
                    },
                    "location": {
                        "type": "string",
                        "description": "Optional event location.",
                    },
                    "all_day": {
                        "type": "boolean",
                        "description": "If true, create an all-day event.",
                    },
                },
                "required": ["title", "start"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_search",
            "description": "Search for events by keyword in title or description.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword."},
                    "days_ahead": {
                        "type": "integer",
                        "description": "Days ahead to search (default 30).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_list_calendars",
            "description": "List available calendars on the CalDAV server.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


# ── Config ────────────────────────────────────────────────────────────────────

def _load_cfg() -> dict:
    try:
        cfg = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8")).get("calendar", {})
    except Exception:
        cfg = {}
    if not cfg.get("password"):
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from hanauta_aipopup.storage import secure_load_secret
            pw = secure_load_secret("skills:calendar:password")
            if pw:
                cfg = dict(cfg)
                cfg["password"] = pw
        except Exception:
            pass
    return cfg


# ── ICS parsing ───────────────────────────────────────────────────────────────

def _parse_ics_dt(value: str) -> datetime | None:
    """Parse an iCalendar DTSTART/DTEND value to a datetime."""
    value = value.strip().split(";")[-1]  # strip TZID= params
    if ":" in value:
        value = value.split(":")[-1]
    fmts = ["%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S", "%Y%m%d"]
    for fmt in fmts:
        try:
            dt = datetime.strptime(value, fmt)
            if fmt.endswith("Z"):
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _parse_ics(text: str) -> list[dict]:
    events: list[dict] = []
    current: dict | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.startswith(" ") or line.startswith("\t"):
            # Continuation line
            if current is not None and "_last_key" in current:
                current[current["_last_key"]] = current.get(current["_last_key"], "") + line[1:]
            continue
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT" and current is not None:
            current.pop("_last_key", None)
            events.append(current)
            current = None
        elif current is not None and ":" in line:
            key, _, val = line.partition(":")
            key_base = key.split(";")[0].upper()
            current[key_base] = val
            current["_last_key"] = key_base
    return events


def _event_to_dict(ev: dict) -> dict:
    return {
        "title": ev.get("SUMMARY", "(no title)"),
        "start": ev.get("DTSTART", ""),
        "end": ev.get("DTEND", ""),
        "description": ev.get("DESCRIPTION", ""),
        "location": ev.get("LOCATION", ""),
        "uid": ev.get("UID", ""),
        "all_day": "T" not in ev.get("DTSTART", "T"),
    }


def _fmt_event(e: dict) -> str:
    start_raw = e.get("start", "")
    dt = _parse_ics_dt(start_raw) if start_raw else None
    all_day = bool(e.get("all_day"))
    date_str = _fmt_dt(dt, all_day) if dt else (start_raw[:16] if start_raw else "?")
    loc = f"  {_locale_label('at')} {e['location']}" if e.get("location") else ""
    return f"{date_str}  {e['title']}{loc}"


def _filter_by_range(events: list[dict], start: datetime, end: datetime) -> list[dict]:
    result = []
    for e in events:
        dt = _parse_ics_dt(e.get("start", ""))
        if dt is None:
            continue
        dt_naive = dt.replace(tzinfo=None) if dt.tzinfo else dt
        if start <= dt_naive <= end:
            result.append(e)
    result.sort(key=lambda x: _parse_ics_dt(x.get("start", "")) or datetime.min)
    return result


# ── CalDAV helpers ────────────────────────────────────────────────────────────

def _caldav_request(cfg: dict, path: str, method: str, body: str = "",
                    extra_headers: dict | None = None) -> tuple[int, str]:
    url = str(cfg.get("url", "")).rstrip("/")
    username = str(cfg.get("username", "")).strip()
    password = str(cfg.get("password", "")).strip()
    full_url = url if not path else urljoin(url + "/", path.lstrip("/"))

    from base64 import b64encode
    token = b64encode(f"{username}:{password}".encode()).decode() if username else ""
    headers: dict[str, str] = {
        "Content-Type": "application/xml; charset=utf-8",
        "Depth": "1",
    }
    if token:
        headers["Authorization"] = f"Basic {token}"
    if extra_headers:
        headers.update(extra_headers)

    data = body.encode("utf-8") if body else None
    req = request.Request(full_url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=15.0) as resp:
            return resp.status, resp.read().decode("utf-8", errors="ignore")
    except error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        raise RuntimeError(f"CalDAV connection failed: {exc}")


def _caldav_report(cfg: dict, start: datetime, end: datetime) -> list[dict]:
    """Fetch events in a time range via REPORT."""
    start_str = start.strftime("%Y%m%dT000000Z")
    end_str = end.strftime("%Y%m%dT235959Z")
    body = f"""<?xml version="1.0" encoding="utf-8" ?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop><D:getetag/><C:calendar-data/></D:prop>
  <C:filter>
    <C:comp-filter name="VCALENDAR">
      <C:comp-filter name="VEVENT">
        <C:time-range start="{start_str}" end="{end_str}"/>
      </C:comp-filter>
    </C:comp-filter>
  </C:filter>
</C:calendar-query>"""
    status, resp_text = _caldav_request(cfg, "", "REPORT", body)
    if status not in (200, 207):
        raise RuntimeError(f"CalDAV REPORT returned HTTP {status}")
    # Extract calendar-data from multistatus response
    events: list[dict] = []
    for ics_block in re.findall(r"BEGIN:VCALENDAR.+?END:VCALENDAR", resp_text, re.DOTALL):
        for ev in _parse_ics(ics_block):
            events.append(_event_to_dict(ev))
    return events


def _caldav_list_calendars(cfg: dict) -> list[str]:
    body = """<?xml version="1.0" encoding="utf-8" ?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop><D:displayname/><C:calendar-description/></D:prop>
</D:propfind>"""
    status, resp_text = _caldav_request(cfg, "", "PROPFIND", body)
    if status not in (200, 207):
        raise RuntimeError(f"CalDAV PROPFIND returned HTTP {status}")
    names = re.findall(r"<[^:>]*:?displayname>([^<]+)</", resp_text)
    return names or ["(no calendars found)"]


def _caldav_create_event(cfg: dict, uid: str, ics: str) -> None:
    url = str(cfg.get("url", "")).rstrip("/")
    path = f"{uid}.ics"
    status, body = _caldav_request(
        cfg, path, "PUT", ics,
        extra_headers={"Content-Type": "text/calendar; charset=utf-8", "If-None-Match": "*"},
    )
    if status not in (200, 201, 204):
        raise RuntimeError(f"CalDAV PUT returned HTTP {status}: {body[:200]}")


# ── ICS file helpers ──────────────────────────────────────────────────────────

def _read_ics_file(cfg: dict) -> list[dict]:
    ics_path = Path(str(cfg.get("ics_path", "")).strip()).expanduser()
    if not ics_path.exists():
        raise RuntimeError(f"ICS file not found: {ics_path}")
    text = ics_path.read_text(encoding="utf-8", errors="ignore")
    return [_event_to_dict(e) for e in _parse_ics(text)]


# ── ICS generation ────────────────────────────────────────────────────────────

def _make_ics(uid: str, title: str, start: str, end: str,
              description: str, location: str, all_day: bool) -> str:
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    if all_day:
        dtstart = f"DTSTART;VALUE=DATE:{start[:10].replace('-', '')}"
        dtend_val = start[:10].replace("-", "")
        dtend = f"DTEND;VALUE=DATE:{dtend_val}"
    else:
        def _fmt(s: str) -> str:
            return s.replace("-", "").replace(":", "").replace(" ", "T")[:15] + "Z"
        dtstart = f"DTSTART:{_fmt(start)}"
        dtend = f"DTEND:{_fmt(end)}"
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Hanauta AI//Calendar Skill//EN",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{now}",
        dtstart, dtend,
        f"SUMMARY:{title}",
    ]
    if description:
        lines.append(f"DESCRIPTION:{description.replace(chr(10), '\\n')}")
    if location:
        lines.append(f"LOCATION:{location}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"


# ── Dispatch ──────────────────────────────────────────────────────────────────

def dispatch(name: str, args: dict) -> str:
    cfg = _load_cfg()
    if not bool(cfg.get("enabled", True)):
        return "[calendar] Skill is disabled in settings."

    backend = str(cfg.get("backend", "caldav")).strip().lower()
    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    try:
        if name == "calendar_list_calendars":
            if backend != "caldav":
                return "[calendar] calendar_list_calendars requires CalDAV backend."
            if not cfg.get("url"):
                return "[calendar] CalDAV URL not configured. Set it in Backend Settings -> Skills -> Calendar."
            cals = _caldav_list_calendars(cfg)
            return _locale_label("calendars") + ":\n" + "\n".join(f"  - {c}" for c in cals)

        if name == "calendar_get_today":
            end = now + timedelta(days=1)
            events = _get_events(cfg, backend, now, end)
            if not events:
                return _locale_label("no_events_today")
            header = _locale_label("today") + " (" + _fmt_dt(now, True) + "):"
            return header + "\n" + "\n".join(_fmt_event(e) for e in events)

        if name == "calendar_get_week":
            monday = now - timedelta(days=now.weekday())
            sunday = monday + timedelta(days=7)
            events = _get_events(cfg, backend, monday, sunday)
            if not events:
                return _locale_label("no_events_week")
            header = _locale_label("this_week") + " (" + _fmt_dt(monday, True) + " - " + _fmt_dt(sunday, True) + "):"
            return header + "\n" + "\n".join(_fmt_event(e) for e in events)

        if name == "calendar_list_events":
            days_ahead = max(1, min(90, int(args.get("days_ahead") or 7)))
            days_back = max(0, min(30, int(args.get("days_back") or 0)))
            limit = max(1, min(100, int(args.get("limit") or 20)))
            start = now - timedelta(days=days_back)
            end = now + timedelta(days=days_ahead)
            events = _get_events(cfg, backend, start, end)[:limit]
            if not events:
                return _locale_label("no_events")
            return "\n".join(_fmt_event(e) for e in events)

        if name == "calendar_search":
            query = str(args.get("query", "")).strip().lower()
            days_ahead = max(1, min(90, int(args.get("days_ahead") or 30)))
            end = now + timedelta(days=days_ahead)
            events = _get_events(cfg, backend, now - timedelta(days=7), end)
            matches = [
                e for e in events
                if query in e.get("title", "").lower()
                or query in e.get("description", "").lower()
            ]
            if not matches:
                return _locale_label("no_matching") + " '" + query + "'."
            return _locale_label("matching") + " '" + query + "':\n" + "\n".join(_fmt_event(e) for e in matches)

        if name == "calendar_create_event":
            if backend == "ics":
                return "[calendar] Creating events is not supported for local ICS files. Use CalDAV."
            if not cfg.get("url"):
                return "[calendar] CalDAV URL not configured."
            title = str(args.get("title", "")).strip()
            start_str = str(args.get("start", "")).strip()
            all_day = bool(args.get("all_day", "T" not in start_str))
            if not start_str:
                return "[calendar] 'start' is required."
            end_str = str(args.get("end", "")).strip()
            if not end_str:
                if all_day:
                    end_str = start_str[:10]
                else:
                    try:
                        dt_start = datetime.fromisoformat(start_str)
                        end_str = (dt_start + timedelta(hours=1)).isoformat()
                    except Exception:
                        end_str = start_str
            import uuid
            uid = str(uuid.uuid4())
            ics = _make_ics(
                uid=uid, title=title, start=start_str, end=end_str,
                description=str(args.get("description", "")),
                location=str(args.get("location", "")),
                all_day=all_day,
            )
            _caldav_create_event(cfg, uid, ics)
            date_label = start_str[:10] if all_day else start_str[:16]
            return _locale_label("event_created") + ": '" + title + "' - " + date_label + "."

    except Exception as exc:
        return f"[calendar] {exc}"

    return f"[calendar] unknown tool: {name}"

def _get_events(cfg: dict, backend: str, start: datetime, end: datetime) -> list[dict]:
    if backend == "ics":
        events = _read_ics_file(cfg)
        return _filter_by_range(events, start, end)
    if not cfg.get("url"):
        raise RuntimeError(
            "CalDAV URL not configured. Set it in Backend Settings → Skills → Calendar."
        )
    return _caldav_report(cfg, start, end)

"""
Home Assistant skill — control entities, read states, trigger automations,
and call services via the HA REST API.

Credentials stored in skills_settings.json under "homeassistant":
    {
        "homeassistant": {
            "enabled": true,
            "url": "http://homeassistant.local:8123",
            "token": "<long-lived access token>"
        }
    }
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib import error, request

_SETTINGS_FILE = (
    Path.home() / ".local" / "state" / "hanauta" / "ai-popup" / "skills_settings.json"
)

SKILL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "ha_get_state",
            "description": "Get the current state and attributes of a Home Assistant entity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "Entity ID, e.g. 'light.living_room' or 'sensor.temperature'.",
                    }
                },
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ha_list_entities",
            "description": "List Home Assistant entities, optionally filtered by domain.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "Optional domain filter: 'light', 'switch', 'sensor', 'climate', 'cover', 'media_player', etc.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max entities to return (default 30).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ha_turn_on",
            "description": "Turn on a Home Assistant entity (light, switch, fan, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string", "description": "Entity ID to turn on."},
                    "brightness_pct": {
                        "type": "integer",
                        "description": "Brightness percentage 0–100 (lights only, optional).",
                    },
                    "color_name": {
                        "type": "string",
                        "description": "Color name e.g. 'red', 'blue', 'warm_white' (lights only, optional).",
                    },
                    "temperature": {
                        "type": "number",
                        "description": "Target temperature in °C (climate only, optional).",
                    },
                },
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ha_turn_off",
            "description": "Turn off a Home Assistant entity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string", "description": "Entity ID to turn off."},
                },
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ha_toggle",
            "description": "Toggle a Home Assistant entity (on→off or off→on).",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string", "description": "Entity ID to toggle."},
                },
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ha_call_service",
            "description": "Call any Home Assistant service with arbitrary data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "Service domain, e.g. 'light', 'climate', 'script'."},
                    "service": {"type": "string", "description": "Service name, e.g. 'turn_on', 'set_temperature'."},
                    "entity_id": {"type": "string", "description": "Target entity ID (optional)."},
                    "data": {
                        "type": "object",
                        "description": "Additional service data as a JSON object (optional).",
                    },
                },
                "required": ["domain", "service"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ha_trigger_automation",
            "description": "Trigger a Home Assistant automation by entity ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "Automation entity ID, e.g. 'automation.morning_routine'.",
                    }
                },
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ha_get_history",
            "description": "Get the recent state history of an entity (last N hours).",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string", "description": "Entity ID."},
                    "hours": {
                        "type": "integer",
                        "description": "How many hours of history to fetch (default 1, max 24).",
                    },
                },
                "required": ["entity_id"],
            },
        },
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_cfg() -> dict:
    try:
        cfg = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8")).get("homeassistant", {})
    except Exception:
        cfg = {}
    # Load token from encrypted storage (set via Backend Settings → Skills)
    if not cfg.get("token"):
        try:
            from pathlib import Path as _P
            import sys as _sys
            _sys.path.insert(0, str(_P(__file__).parent.parent))
            from hanauta_aipopup.storage import secure_load_secret
            token = secure_load_secret("skills:homeassistant:token")
            if token:
                cfg = dict(cfg)
                cfg["token"] = token
        except Exception:
            pass
    return cfg


def _api(cfg: dict, path: str, method: str = "GET", body: dict | None = None) -> object:
    url = str(cfg.get("url", "")).rstrip("/")
    token = str(cfg.get("token", "")).strip()
    if not url:
        raise RuntimeError("Home Assistant URL not configured. Set it in Backend Settings → Skills → Home Assistant.")
    if not token:
        raise RuntimeError("Home Assistant token not configured. Set it in Backend Settings → Skills → Home Assistant.")
    full_url = f"{url}/api{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode() if body is not None else None
    req = request.Request(full_url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=10.0) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except error.HTTPError as exc:
        raise RuntimeError(f"HA API error {exc.code}: {exc.read().decode('utf-8', errors='ignore')[:200]}")
    except Exception as exc:
        raise RuntimeError(f"HA connection failed: {exc}")


def _fmt_state(s: dict) -> str:
    eid = s.get("entity_id", "?")
    state = s.get("state", "?")
    attrs = s.get("attributes", {})
    friendly = attrs.get("friendly_name", "")
    label = f"{friendly} ({eid})" if friendly else eid
    extras = []
    for key in ("brightness", "color_temp", "temperature", "current_temperature",
                "humidity", "unit_of_measurement", "device_class"):
        if key in attrs:
            val = attrs[key]
            unit = attrs.get("unit_of_measurement", "") if key != "unit_of_measurement" else ""
            extras.append(f"{key}={val}{unit}")
    extra_str = "  [" + ", ".join(extras) + "]" if extras else ""
    return f"{label}: {state}{extra_str}"


# ── Dispatch ──────────────────────────────────────────────────────────────────

def dispatch(name: str, args: dict) -> str:
    cfg = _load_cfg()
    if not bool(cfg.get("enabled", True)):
        return "[homeassistant] Skill is disabled in settings."

    try:
        if name == "ha_get_state":
            eid = str(args["entity_id"]).strip()
            state = _api(cfg, f"/states/{eid}")
            return _fmt_state(state)  # type: ignore[arg-type]

        if name == "ha_list_entities":
            domain = str(args.get("domain") or "").strip().lower()
            limit = int(args.get("limit") or 30)
            states = _api(cfg, "/states")
            if not isinstance(states, list):
                return "[ha] Unexpected response from /api/states"
            if domain:
                states = [s for s in states if str(s.get("entity_id", "")).startswith(f"{domain}.")]
            states = states[:limit]
            if not states:
                return f"No entities found{' for domain ' + domain if domain else ''}."
            return "\n".join(_fmt_state(s) for s in states)

        if name == "ha_turn_on":
            eid = str(args["entity_id"]).strip()
            domain = eid.split(".")[0]
            data: dict = {"entity_id": eid}
            if args.get("brightness_pct") is not None:
                data["brightness_pct"] = int(args["brightness_pct"])
            if args.get("color_name"):
                data["color_name"] = str(args["color_name"]).strip()
            if args.get("temperature") is not None:
                data["temperature"] = float(args["temperature"])
            _api(cfg, f"/services/{domain}/turn_on", method="POST", body=data)
            return f"Turned on {eid}."

        if name == "ha_turn_off":
            eid = str(args["entity_id"]).strip()
            domain = eid.split(".")[0]
            _api(cfg, f"/services/{domain}/turn_off", method="POST", body={"entity_id": eid})
            return f"Turned off {eid}."

        if name == "ha_toggle":
            eid = str(args["entity_id"]).strip()
            domain = eid.split(".")[0]
            _api(cfg, f"/services/{domain}/toggle", method="POST", body={"entity_id": eid})
            return f"Toggled {eid}."

        if name == "ha_call_service":
            domain = str(args["domain"]).strip()
            service = str(args["service"]).strip()
            body: dict = dict(args.get("data") or {})
            if args.get("entity_id"):
                body["entity_id"] = str(args["entity_id"]).strip()
            _api(cfg, f"/services/{domain}/{service}", method="POST", body=body)
            return f"Called {domain}.{service}" + (f" on {body.get('entity_id')}" if body.get("entity_id") else "") + "."

        if name == "ha_trigger_automation":
            eid = str(args["entity_id"]).strip()
            _api(cfg, "/services/automation/trigger", method="POST", body={"entity_id": eid})
            return f"Triggered automation {eid}."

        if name == "ha_get_history":
            eid = str(args["entity_id"]).strip()
            hours = max(1, min(24, int(args.get("hours") or 1)))
            import datetime
            start = (datetime.datetime.utcnow() - datetime.timedelta(hours=hours)).isoformat()
            result = _api(cfg, f"/history/period/{start}?filter_entity_id={eid}&minimal_response=true")
            if not isinstance(result, list) or not result:
                return f"No history found for {eid} in the last {hours}h."
            entries = result[0] if isinstance(result[0], list) else result
            lines = []
            for entry in entries[-20:]:  # last 20 state changes
                ts = str(entry.get("last_changed", ""))[:19].replace("T", " ")
                state = entry.get("state", "?")
                lines.append(f"  {ts}  →  {state}")
            return f"History for {eid} (last {hours}h, {len(entries)} changes):\n" + "\n".join(lines)

    except Exception as exc:
        return f"[homeassistant] {exc}"

    return f"[homeassistant] unknown tool: {name}"

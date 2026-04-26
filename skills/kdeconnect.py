"""KDE Connect skill — interact with paired Android/iOS devices via kdeconnect-cli."""
from __future__ import annotations

import subprocess

SKILL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "kdeconnect_list_devices",
            "description": "List all paired KDE Connect devices and their reachability.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kdeconnect_battery",
            "description": "Get the battery level of a paired device.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device": {"type": "string", "description": "Device name or ID (leave empty for first reachable device)."}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kdeconnect_ping",
            "description": "Send a ping notification to a paired device.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device": {"type": "string", "description": "Device name or ID."},
                    "message": {"type": "string", "description": "Optional ping message."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kdeconnect_ring",
            "description": "Ring a paired phone to help find it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device": {"type": "string", "description": "Device name or ID."}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kdeconnect_send_sms",
            "description": "Send an SMS via a paired Android phone.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device": {"type": "string", "description": "Device name or ID."},
                    "number": {"type": "string", "description": "Phone number to send SMS to."},
                    "message": {"type": "string", "description": "SMS text."},
                },
                "required": ["number", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kdeconnect_share_file",
            "description": "Share a local file to a paired device.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device": {"type": "string", "description": "Device name or ID."},
                    "path": {"type": "string", "description": "Absolute path to the file to share."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kdeconnect_share_url",
            "description": "Open a URL on a paired device.",
            "parameters": {
                "type": "object",
                "properties": {
                    "device": {"type": "string", "description": "Device name or ID."},
                    "url": {"type": "string", "description": "URL to open on the device."},
                },
                "required": ["url"],
            },
        },
    },
]


def _run(cmd: list[str], timeout: float = 8.0) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    if result.returncode != 0:
        raise RuntimeError(err or out or f"exit {result.returncode}")
    return out or "(done)"


def _list_all_devices() -> list[tuple[str, str]]:
    """Return list of (device_id, device_name) for all paired devices."""
    raw = subprocess.run(
        ["kdeconnect-cli", "--list-devices"],
        capture_output=True, text=True, timeout=5, check=False,
    ).stdout.strip()
    devices = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        dev_id = parts[0] if parts else ""
        name = parts[1] if len(parts) > 1 else ""
        devices.append((dev_id, name))
    return devices


def _resolve_device(hint: str) -> str:
    """Return a device ID matching the hint, or the first reachable device."""
    devices = _list_all_devices()
    if not devices:
        raise RuntimeError("No KDE Connect devices found.")

    # Clean up hint
    hint_clean = hint.strip().lower()
    # Remove common prefixes like "my ", "the ", "phone", "手机"
    for prefix in ("my ", "the ", "phone", "mobile", "android", "ios", "智能手机", "手机"):
        if hint_clean.startswith(prefix):
            hint_clean = hint_clean[len(prefix):].strip()

    # Try to get first reachable device if no hint
    if not hint_clean:
        raw = subprocess.run(
            ["kdeconnect-cli", "--list-available", "--id-only"],
            capture_output=True, text=True, timeout=5, check=False,
        ).stdout.strip()
        available = [line.strip() for line in raw.splitlines() if line.strip()]
        if available:
            return available[0]
        return devices[0][0]

    # Score-based matching: higher is better match
    def _score(dev_name: str) -> int:
        name_lower = dev_name.lower()
        score = 0
        # Exact substring match
        if hint_clean in name_lower:
            score += 100
        # Word-by-word match
        hint_words = hint_clean.split()
        for word in hint_words:
            if word in name_lower:
                score += 50
        # Partial match: "poco" in "poco m4 5g" or "m4" in "poco m4 5g"
        for word in hint_words:
            for part in name_lower.split():
                if word.startswith(part) or part.startswith(word):
                    score += 25
        # Prefer phones (contain phone-related keywords)
        phone_keywords = ("phone", "mobile", "android", "poco", "oneplus", "samsung", "xiaomi", "pixel", "iphone")
        for kw in phone_keywords:
            if kw in name_lower:
                score += 10
        return score

    best_id = devices[0][0]
    best_score = -1
    for dev_id, dev_name in devices:
        score = _score(dev_name)
        if score > best_score:
            best_score = score
            best_id = dev_id

    # If no good match, try first available
    if best_score < 10:
        raw = subprocess.run(
            ["kdeconnect-cli", "--list-available", "--id-only"],
            capture_output=True, text=True, timeout=5, check=False,
        ).stdout.strip()
        available = [line.strip() for line in raw.splitlines() if line.strip()]
        if available:
            best_id = available[0]

    return best_id


def dispatch(name: str, args: dict) -> str:
    try:
        if name == "kdeconnect_list_devices":
            return _run(["kdeconnect-cli", "--list-devices"])

        device_hint = str(args.get("device") or "").strip()

        if name == "kdeconnect_battery":
            dev = _resolve_device(device_hint)
            return _run(["kdeconnect-cli", "--device", dev, "--battery"])

        if name == "kdeconnect_ping":
            dev = _resolve_device(device_hint)
            msg = str(args.get("message") or "Ping from Hanauta AI").strip()
            return _run(["kdeconnect-cli", "--device", dev, "--ping-msg", msg])

        if name == "kdeconnect_ring":
            dev = _resolve_device(device_hint)
            return _run(["kdeconnect-cli", "--device", dev, "--ring"])

        if name == "kdeconnect_send_sms":
            dev = _resolve_device(device_hint)
            number = str(args["number"]).strip()
            message = str(args["message"]).strip()
            return _run(["kdeconnect-cli", "--device", dev, "--send-sms", message, "--destination", number])

        if name == "kdeconnect_share_file":
            from pathlib import Path
            dev = _resolve_device(device_hint)
            path = Path(str(args["path"]).strip()).expanduser()
            if not path.exists():
                return f"File not found: {path}"
            return _run(["kdeconnect-cli", "--device", dev, "--share", str(path)])

        if name == "kdeconnect_share_url":
            dev = _resolve_device(device_hint)
            url = str(args["url"]).strip()
            return _run(["kdeconnect-cli", "--device", dev, "--share", url])

    except FileNotFoundError:
        return "[kdeconnect] kdeconnect-cli not found. Install kdeconnect."
    except Exception as exc:
        return f"[kdeconnect] {exc}"

    return f"[kdeconnect] unknown tool: {name}"

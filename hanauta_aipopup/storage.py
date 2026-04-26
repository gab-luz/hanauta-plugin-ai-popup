# Storage: encrypted secrets and chat history
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import TYPE_CHECKING

from cryptography.fernet import Fernet, InvalidToken

from .runtime import AI_STATE_DIR, SECURE_DB_FILE, SECURE_KEY_FILE

if TYPE_CHECKING:
    from .models import ChatItemData, SourceChipData


def _chmod_private(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def _cipher() -> Fernet:
    AI_STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not SECURE_KEY_FILE.exists():
        SECURE_KEY_FILE.write_bytes(Fernet.generate_key())
        _chmod_private(SECURE_KEY_FILE)
    key = SECURE_KEY_FILE.read_bytes()
    _chmod_private(SECURE_KEY_FILE)
    return Fernet(key)


def _secure_db() -> sqlite3.Connection:
    AI_STATE_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(SECURE_DB_FILE)
    connection.execute("CREATE TABLE IF NOT EXISTS secrets (name TEXT PRIMARY KEY, payload BLOB NOT NULL)")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS chat_history (id INTEGER PRIMARY KEY AUTOINCREMENT, payload BLOB NOT NULL, created_at REAL NOT NULL)"
    )
    connection.commit()
    _chmod_private(SECURE_DB_FILE)
    return connection


def _encrypt_payload(payload: dict) -> bytes:
    return _cipher().encrypt(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def _decrypt_payload(blob: bytes) -> dict:
    data = _cipher().decrypt(blob)
    return json.loads(data.decode("utf-8"))


def _chat_timestamp_label(timestamp_value: object) -> str:
    try:
        stamp = float(timestamp_value or 0.0)
    except Exception:
        return ""
    if stamp <= 0:
        return ""
    try:
        return time.strftime("%H:%M", time.localtime(stamp))
    except Exception:
        return ""


def secure_store_secret(name: str, value: str) -> None:
    conn = _secure_db()
    try:
        if value.strip():
            conn.execute(
                "INSERT INTO secrets(name, payload) VALUES(?, ?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload",
                (name, _encrypt_payload({"value": value})),
            )
        else:
            conn.execute("DELETE FROM secrets WHERE name = ?", (name,))
        conn.commit()
    finally:
        conn.close()


def secure_load_secret(name: str) -> str:
    conn = _secure_db()
    try:
        row = conn.execute("SELECT payload FROM secrets WHERE name = ?", (name,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return ""
    try:
        return str(_decrypt_payload(row[0]).get("value", ""))
    except (InvalidToken, json.JSONDecodeError, TypeError, ValueError):
        return ""


def secure_append_chat(item: "ChatItemData") -> None:
    from .models import ChatItemData, SourceChipData
    conn = _secure_db()
    try:
        conn.execute(
            "INSERT INTO chat_history(payload, created_at) VALUES(?, ?)",
            (_encrypt_payload({
                "role": item.role,
                "title": item.title,
                "body": item.body,
                "meta": item.meta,
                "created_at": float(item.created_at or time.time()),
                "chips": [c.text for c in item.chips],
                "audio_path": item.audio_path,
                "audio_waveform": [int(v) for v in item.audio_waveform],
            }), float(item.created_at or time.time())),
        )
        conn.commit()
    finally:
        conn.close()


def secure_load_chat_history() -> list["ChatItemData"]:
    from .models import ChatItemData, SourceChipData
    conn = _secure_db()
    try:
        rows = conn.execute("SELECT payload, created_at FROM chat_history ORDER BY id ASC").fetchall()
    finally:
        conn.close()
    history = []
    for row in rows:
        try:
            payload = _decrypt_payload(row[0])
        except (InvalidToken, json.JSONDecodeError, TypeError, ValueError):
            continue
        chips_raw = payload.get("chips", [])
        chips = [SourceChipData(str(c)) for c in chips_raw if str(c).strip()] if isinstance(chips_raw, list) else []
        waveform_raw = payload.get("audio_waveform", [])
        waveform = [max(0, min(100, int(v))) for v in waveform_raw if isinstance(v, (int, float, str))] if isinstance(waveform_raw, list) else []
        history.append(ChatItemData(
            role=str(payload.get("role", "assistant")),
            title=str(payload.get("title", "")),
            body=str(payload.get("body", "")),
            meta=str(payload.get("meta", "")),
            created_at=float(payload.get("created_at", row[1] or time.time()) or time.time()),
            chips=chips,
            audio_path=str(payload.get("audio_path", "")),
            audio_waveform=waveform,
        ))
    return history


def secure_clear_chat_history() -> None:
    conn = _secure_db()
    try:
        conn.execute("DELETE FROM chat_history")
        conn.commit()
    finally:
        conn.close()


def _chat_export_payload(items: list["ChatItemData"]) -> dict[str, object]:
    import html
    import re
    return {
        "format": "hanauta-chat-export-v1",
        "exported_at": time.time(),
        "messages": [
            {
                "role": item.role,
                "title": item.title,
                "meta": item.meta,
                "timestamp": float(item.created_at or time.time()),
                "timestamp_label": _chat_timestamp_label(item.created_at),
                "body_html": item.body,
                "audio_path": item.audio_path,
                "chips": [chip.text for chip in item.chips],
            }
            for item in items
        ],
        "plain_text": "\n\n".join(
            f"[{_chat_timestamp_label(item.created_at) or '--:--'}] {item.title or item.role}: "
            f"{re.sub(r'<[^>]+>', ' ', html.unescape(item.body)).strip()}"
            for item in items
        ).strip(),
    }


def archive_chat_history(items: list["ChatItemData"]) -> Path:
    from .runtime import CHAT_ARCHIVES_DIR
    CHAT_ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    path = CHAT_ARCHIVES_DIR / f"hanauta-chat-archive-{stamp}.json"
    path.write_text(json.dumps(_chat_export_payload(items), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def list_chat_archives() -> list[dict]:
    from .runtime import CHAT_ARCHIVES_DIR
    CHAT_ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)
    archives = []
    for p in sorted(CHAT_ARCHIVES_DIR.glob("hanauta-chat-archive-*.json"), reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            archives.append({
                "path": str(p),
                "filename": p.name,
                "exported_at": data.get("exported_at", 0),
                "message_count": len(data.get("messages", [])),
                "plain_text": data.get("plain_text", "")[:100],
            })
        except Exception:
            continue
    return archives


def load_chat_archive(path: str) -> list["ChatItemData"] | None:
    from .models import ChatItemData, SourceChipData
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None
    history = []
    for msg in data.get("messages", []):
        timestamp = msg.get("timestamp", time.time())
        chips = [SourceChipData(str(c)) for c in msg.get("chips", []) if str(c).strip()]
        history.append(ChatItemData(
            role=str(msg.get("role", "assistant")),
            title=str(msg.get("title", "")),
            body=str(msg.get("body_html", "")),
            meta=str(msg.get("meta", "")),
            created_at=timestamp,
            chips=chips,
            audio_path=str(msg.get("audio_path", "")),
            audio_waveform=[],
        ))
    return history


__all__ = [
    "secure_store_secret",
    "secure_load_secret",
    "secure_append_chat",
    "secure_load_chat_history",
    "secure_clear_chat_history",
    "_chat_timestamp_label",
    "_chat_export_payload",
    "archive_chat_history",
    "list_chat_archives",
    "load_chat_archive",
]
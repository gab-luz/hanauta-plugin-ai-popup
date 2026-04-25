# Characters: character loading and management
from __future__ import annotations

import json
import shutil
import time
import zlib
from base64 import b64decode
from pathlib import Path

from .models import CharacterCard
from .runtime import CHARACTER_AVATARS_DIR, CHARACTER_LIBRARY_FILE


def _safe_slug(value: str) -> str:
    raw = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.strip())
    return "_".join(p for p in raw.split("_") if p)[:80] or "audio"


def _sanitize_character_id(name: str) -> str:
    return f"{_safe_slug(name.lower())}_{int(time.time() * 1000)}"


def _character_from_payload(payload: dict) -> CharacterCard:
    return CharacterCard(
        id=str(payload.get("id", "")).strip() or _sanitize_character_id(str(payload.get("name", "character"))),
        name=str(payload.get("name", "Unnamed character")).strip() or "Unnamed character",
        description=str(payload.get("description", "")).strip(),
        personality=str(payload.get("personality", "")).strip(),
        scenario=str(payload.get("scenario", "")).strip(),
        first_message=str(payload.get("first_message", payload.get("first_mes", ""))).strip(),
        message_example=str(payload.get("message_example", payload.get("mes_example", ""))).strip(),
        system_prompt=str(payload.get("system_prompt", "")).strip(),
        avatar_path=str(payload.get("avatar_path", "")).strip(),
        source_path=str(payload.get("source_path", "")).strip(),
        source_type=str(payload.get("source_type", "")).strip(),
    )


def load_character_library() -> tuple[list[CharacterCard], str]:
    try:
        payload = json.loads(CHARACTER_LIBRARY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return [], ""
    cards_raw = payload.get("cards", [])
    cards = []
    if isinstance(cards_raw, list):
        for row in cards_raw:
            if isinstance(row, dict):
                cards.append(_character_from_payload(row))
    active_id = str(payload.get("active_id", "")).strip()
    if active_id and not any(c.id == active_id for c in cards):
        active_id = ""
    return cards, active_id


def save_character_library(cards: list[CharacterCard], active_id: str):
    from .runtime import AI_STATE_DIR
    AI_STATE_DIR.mkdir(parents=True, exist_ok=True)
    CHARACTER_AVATARS_DIR.mkdir(parents=True, exist_ok=True)
    CHARACTER_LIBRARY_FILE.write_text(json.dumps({
        "active_id": active_id if any(c.id == active_id for c in cards) else "",
        "cards": [{
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "personality": c.personality,
            "scenario": c.scenario,
            "first_message": c.first_message,
            "message_example": c.message_example,
            "system_prompt": c.system_prompt,
            "avatar_path": c.avatar_path,
            "source_path": c.source_path,
            "source_type": c.source_type,
        } for c in cards]
    }, indent=2, ensure_ascii=False), encoding="utf-8")


def _decode_character_json_text(raw: str) -> dict:
    from urllib.parse import unquote
    text = raw.strip()
    if not text:
        raise ValueError("Empty character payload.")
    for candidate in [text, unquote(text) if "%" in text else None]:
        if candidate:
            try:
                val = json.loads(candidate)
                if isinstance(val, dict):
                    return val
            except Exception:
                pass
    try:
        dec = b64decode(text).decode("utf-8", errors="ignore").strip()
        if dec:
            val = json.loads(dec)
            if isinstance(val, dict):
                return val
    except Exception:
        pass
    raise ValueError("Could not decode character JSON.")


def _extract_tavern_png_payload(path: Path) -> dict:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Not a PNG file.")
    offset = 8
    candidates = []
    valid = {b"chara", b"character", b"ccv3"}
    while offset + 8 <= len(data):
        length = int.from_bytes(data[offset:offset + 4], "big")
        chunk_type = data[offset + 4:offset + 8]
        start, end = offset + 8, start + length
        if end + 4 > len(data):
            break
        chunk = data[start:end]
        if chunk_type == b"tEXt":
            try:
                k, v = chunk.split(b"\x00", 1)
                if k in valid:
                    candidates.append(v.decode("utf-8", errors="ignore"))
            except Exception:
                pass
        elif chunk_type == b"zTXt":
            try:
                k, rest = chunk.split(b"\x00", 1)
                if k in valid and rest:
                    if rest[0] == 0:
                        candidates.append(zlib.decompress(rest[1:]).decode("utf-8", errors="ignore"))
            except Exception:
                pass
        offset = end + 4
    for c in candidates:
        try:
            return _decode_character_json_text(c)
        except Exception:
            continue
    raise ValueError("No TavernAI/KoboldCPP character found.")


def _normalize_imported_character(payload: dict, source_path: Path, source_type: str) -> CharacterCard:
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        raise ValueError("Invalid character payload.")
    name = str(data.get("name", payload.get("name", ""))).strip() or source_path.stem
    card = CharacterCard(
        id=_sanitize_character_id(name),
        name=name,
        description=str(data.get("description", payload.get("description", ""))).strip(),
        personality=str(data.get("personality", payload.get("personality", ""))).strip(),
        scenario=str(data.get("scenario", payload.get("scenario", ""))).strip(),
        first_message=str(data.get("first_mes", data.get("first_message", payload.get("first_mes", "")))).strip(),
        message_example=str(data.get("mes_example", data.get("message_example", payload.get("mes_example", "")))).strip(),
        system_prompt=str(data.get("system_prompt", data.get("post_history_instructions", payload.get("system_prompt", "")))).strip(),
        source_path=str(source_path),
        source_type=source_type,
    )
    avatar_src = source_path if source_path.suffix.lower() == ".png" else None
    if not avatar_src:
        avatar_field = str(data.get("avatar", payload.get("avatar", ""))).strip()
        if avatar_field:
            guessed = Path(avatar_field).expanduser()
            if not guessed.is_absolute():
                guessed = source_path.parent / guessed
            if guessed.exists():
                avatar_src = guessed
    if avatar_src and avatar_src.exists():
        CHARACTER_AVATARS_DIR.mkdir(parents=True, exist_ok=True)
        target = CHARACTER_AVATARS_DIR / f"{card.id}{avatar_src.suffix.lower() or '.png'}"
        try:
            shutil.copy2(str(avatar_src), str(target))
            card.avatar_path = str(target)
        except Exception:
            card.avatar_path = ""
    return card


def import_character_from_file(path: Path) -> CharacterCard:
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Character JSON must be an object.")
        return _normalize_imported_character(payload, path, "json")
    if suffix == ".png":
        return _normalize_imported_character(_extract_tavern_png_payload(path), path, "png")
    raise ValueError("Unsupported character format. Use .json or .png")


def _character_compose_prompt(card: CharacterCard) -> str:
    parts = []
    for field in [card.system_prompt, card.description, card.personality, card.scenario, card.first_message]:
        if field:
            parts.append(field)
    return "\n".join(parts)


def _chat_messages_for_prompt(prompt: str, character: CharacterCard | None, emotion_tags: bool = False) -> list[dict]:
    system = "You are Hanauta AI. Keep spoken replies concise, natural, and easy to listen to."
    if character:
        char_prompt = _character_compose_prompt(character).strip()
        if char_prompt:
            system = f"{system}\n\nActive character:\n{char_prompt}"
    if emotion_tags:
        system = f"{system}\n\nBefore each reply, add exactly one emotion tag like [neutral], [happy], etc."
    return [{"role": "system", "content": system}, {"role": "user", "content": prompt}]


__all__ = [
    "load_character_library",
    "save_character_library",
    "import_character_from_file",
    "_character_from_payload",
    "_character_compose_prompt",
    "_sanitize_character_id",
    "_decode_character_json_text",
    "_extract_tavern_png_payload",
    "_normalize_imported_character",
    "_chat_messages_for_prompt",
]
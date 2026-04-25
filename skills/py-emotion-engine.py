"""
Hanauta AI — Emotion Engine skill.

Tracks the user's emotional state across the conversation and exposes it
to all other skills so they can adapt their tone and urgency.

The engine works at two levels:
  1. Passive inference  — analyses the user's last message for emotional cues
     (text sentiment, punctuation, keywords, voice RMS if available).
  2. Active state store — persists the current emotion + intensity so any
     skill can read it via `emotion_get_state`.

Other skills import the helpers directly:
    from skills.py_emotion_engine import current_emotion, emotion_context_line
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

_STATE_FILE = Path.home() / ".local" / "state" / "hanauta" / "ai-popup" / "emotion_state.json"

# ── Emotion taxonomy ──────────────────────────────────────────────────────────
EMOTIONS = {
    "neutral", "happy", "sad", "angry", "anxious", "excited",
    "frustrated", "calm", "playful", "tired", "confused", "surprised",
    "affectionate", "serious", "embarrassed", "teasing", "flirty", "shy",
}

# Keyword → (emotion, intensity_boost)
_KEYWORD_MAP: list[tuple[re.Pattern, str, float]] = [
    (re.compile(r"\b(great|awesome|love|amazing|fantastic|yay|woohoo)\b", re.I), "happy", 0.3),
    (re.compile(r"\b(sad|miss|lonely|cry|crying|tears|heartbroken)\b", re.I), "sad", 0.3),
    (re.compile(r"\b(angry|furious|hate|damn|wtf|pissed|rage)\b", re.I), "angry", 0.4),
    (re.compile(r"\b(anxious|worried|nervous|scared|afraid|panic)\b", re.I), "anxious", 0.35),
    (re.compile(r"\b(excited|can't wait|thrilled|pumped|stoked)\b", re.I), "excited", 0.3),
    (re.compile(r"\b(tired|exhausted|sleepy|drained|worn out)\b", re.I), "tired", 0.25),
    (re.compile(r"\b(confused|lost|don't understand|what\?|huh)\b", re.I), "confused", 0.2),
    (re.compile(r"\b(frustrated|ugh|argh|seriously|come on)\b", re.I), "frustrated", 0.3),
    (re.compile(r"\b(haha|lol|lmao|rofl|😂|😄|😁)\b", re.I), "playful", 0.2),
    (re.compile(r"\b(calm|relax|peace|chill|breathe)\b", re.I), "calm", 0.2),
    (re.compile(r"[!]{2,}"), "excited", 0.15),
    (re.compile(r"[?]{2,}"), "confused", 0.15),
    (re.compile(r"\.{3,}"), "sad", 0.1),
]

_DEFAULT_STATE: dict = {
    "emotion": "neutral",
    "intensity": 0.5,
    "updated_at": 0.0,
    "history": [],
}


# ── Persistence ───────────────────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return dict(_DEFAULT_STATE)


def _save_state(state: dict) -> None:
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ── Public helpers (imported by other skills) ─────────────────────────────────

def current_emotion() -> tuple[str, float]:
    """Return (emotion_name, intensity 0.0–1.0) from the persisted state."""
    state = _load_state()
    return str(state.get("emotion", "neutral")), float(state.get("intensity", 0.5))


def emotion_context_line() -> str:
    """
    One-line context string for injection into other skill prompts.
    e.g. "User is currently feeling anxious (intensity 0.72)."
    """
    emotion, intensity = current_emotion()
    if emotion == "neutral":
        return ""
    return f"User is currently feeling {emotion} (intensity {intensity:.2f}). Adapt your tone accordingly."


def infer_emotion(text: str) -> tuple[str, float]:
    """
    Infer emotion from a text string.
    Returns (emotion, intensity).
    """
    scores: dict[str, float] = {}
    for pattern, emotion, boost in _KEYWORD_MAP:
        if pattern.search(text):
            scores[emotion] = scores.get(emotion, 0.0) + boost

    # Caps and exclamation amplify intensity
    caps_ratio = sum(1 for c in text if c.isupper()) / max(len(text), 1)
    if caps_ratio > 0.4:
        for k in scores:
            scores[k] = min(1.0, scores[k] + 0.15)

    if not scores:
        return "neutral", 0.5

    top_emotion = max(scores, key=lambda k: scores[k])
    intensity = min(1.0, 0.4 + scores[top_emotion])
    return top_emotion, round(intensity, 3)


# ── Skill definitions ─────────────────────────────────────────────────────────

SKILL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "emotion_get_state",
            "description": (
                "Get the user's current detected emotional state and intensity. "
                "Use this to adapt your tone before responding."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "emotion_update",
            "description": (
                "Update the user's emotional state based on what you observed in their message. "
                "Call this after each user message to keep the emotion engine current."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "emotion": {
                        "type": "string",
                        "description": f"One of: {', '.join(sorted(EMOTIONS))}",
                    },
                    "intensity": {
                        "type": "number",
                        "description": "Intensity from 0.0 (barely) to 1.0 (very strongly).",
                    },
                    "source_text": {
                        "type": "string",
                        "description": "The user message that triggered this update (optional, used for auto-inference if emotion is omitted).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "emotion_history",
            "description": "Return the last N emotional states to understand how the user's mood has shifted.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of past states to return (default 5)."},
                },
                "required": [],
            },
        },
    },
]


def dispatch(name: str, args: dict) -> str:
    if name == "emotion_get_state":
        state = _load_state()
        emotion = str(state.get("emotion", "neutral"))
        intensity = float(state.get("intensity", 0.5))
        age = time.time() - float(state.get("updated_at", 0.0))
        age_str = f"{int(age)}s ago" if age < 120 else f"{int(age / 60)}m ago"
        ctx = emotion_context_line()
        return (
            f"emotion={emotion}  intensity={intensity:.2f}  updated={age_str}\n"
            + (ctx if ctx else "User appears neutral.")
        )

    if name == "emotion_update":
        state = _load_state()
        source = str(args.get("source_text", "")).strip()
        emotion = str(args.get("emotion", "")).strip().lower()
        intensity = args.get("intensity")

        if emotion not in EMOTIONS:
            if source:
                emotion, inferred_intensity = infer_emotion(source)
                if intensity is None:
                    intensity = inferred_intensity
            else:
                emotion = "neutral"

        intensity = float(intensity) if intensity is not None else 0.5
        intensity = max(0.0, min(1.0, intensity))

        history: list = state.get("history", [])
        history.append({
            "emotion": state.get("emotion", "neutral"),
            "intensity": state.get("intensity", 0.5),
            "at": state.get("updated_at", 0.0),
        })
        state["history"] = history[-20:]  # keep last 20
        state["emotion"] = emotion
        state["intensity"] = intensity
        state["updated_at"] = time.time()
        _save_state(state)
        return f"Emotion updated: {emotion} (intensity {intensity:.2f})"

    if name == "emotion_history":
        state = _load_state()
        limit = int(args.get("limit") or 5)
        history = list(reversed(state.get("history", [])))[:limit]
        if not history:
            return "No emotion history yet."
        lines = []
        for entry in history:
            ts = float(entry.get("at", 0.0))
            age = int(time.time() - ts)
            age_str = f"{age}s ago" if age < 120 else f"{age // 60}m ago"
            lines.append(f"{entry.get('emotion','?')} ({entry.get('intensity',0):.2f}) — {age_str}")
        return "\n".join(lines)

    return f"[emotion] unknown tool: {name}"

"""Lutris skill — list games, show play time, and launch games.

Lutris is a Linux game launcher that manages games from various sources (Steam, GOG, Wine, emulators, etc.).

Requires lutris to be installed. No API key needed.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

SKILL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "lutris_list_games",
            "description": "List all games in the Lutris library with their play time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "installed_only": {
                        "type": "boolean",
                        "description": "Only show installed games (default false).",
                    },
                    "limit": {"type": "integer", "description": "Max games to show (default 20)."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lutris_currently_playing",
            "description": "Show if any game is currently running via Lutris.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lutris_run_game",
            "description": "Launch a game by ID or slug.",
            "parameters": {
                "type": "object",
                "properties": {
                    "game_id": {"type": "string", "description": "Numeric ID or slug of the game to launch."},
                },
                "required": ["game_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lutris_playtime",
            "description": "Show total play time across all games, or per-game stats.",
            "parameters": {
                "type": "object",
                "properties": {
                    "game_id": {"type": "string", "description": "Optional game ID to show stats for."},
                },
                "required": [],
            },
        },
    },
]


def _run_lutris(args: list[str], timeout: int = 30) -> str:
    cmd = ["lutris"] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0 and result.stderr:
            return result.stderr.strip()
        return result.stdout
    except subprocess.TimeoutExpired:
        return "Lutris command timed out."
    except FileNotFoundError:
        return "Lutris is not installed."
    except Exception as e:
        return f"Error: {e}"


def _load_games(installed_only: bool = False) -> list[dict]:
    args = ["--list-games", "--json"]
    if installed_only:
        args.append("--installed")
    output = _run_lutris(args)
    if not output:
        return []
    lines = output.splitlines()
    json_started = False
    json_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            json_started = True
        if json_started:
            json_lines.append(line)
    if not json_lines:
        return []
    json_str = "\n".join(json_lines).strip()
    if not json_str:
        return []
    try:
        games = json.loads(json_str)
        if isinstance(games, list):
            return games
    except json.JSONDecodeError as e:
        pass
    return []


def _fmt_playtime(playtime_str: str | None) -> str:
    if not playtime_str:
        return "never"
    return playtime_str


def dispatch(name: str, args: dict) -> str:
    try:
        if name == "lutris_list_games":
            installed_only = bool(args.get("installed_only", False))
            limit = int(args.get("limit", 20))
            games = _load_games(installed_only)
            if not games:
                return "No games found in Lutris library."
            games = games[:limit]
            lines = ["Lutris games:"]
            for g in games:
                name_ = g.get("name", "?")
                runner = g.get("runner", "?")
                playtime = _fmt_playtime(g.get("playtime"))
                last = (g.get("lastplayed") or "")[:10] or "never"
                gid = g.get("id", "")
                lines.append(f"[{gid}] {name_} ({runner}) - {playtime} last: {last}")
            return "\n".join(lines)

        if name == "lutris_currently_playing":
            games = _load_games()
            if not games:
                return "No games in library."
            recent = [g for g in games if g.get("lastplayed")]
            if not recent:
                return "No recently played games."
            recent.sort(key=lambda g: g.get("lastplayed", ""), reverse=True)
            latest = recent[0]
            name_ = latest.get("name", "?")
            runner = latest.get("runner", "?")
            last = latest.get("lastplayed", "")[:19] or "?"
            return f"Last played: {name_} ({runner}) at {last}"

        if name == "lutris_run_game":
            game_id = str(args.get("game_id", "")).strip()
            if not game_id:
                return "game_id is required."
            output = _run_lutris([f"lutris:rungameid/{game_id}"])
            if output and output.startswith("Error"):
                output2 = _run_lutris([f"lutris:rungame/{game_id}"])
                if output2 and not output2.startswith("Error"):
                    return f"Launching {game_id}..."
            return f"Launching {game_id}..."

        if name == "lutris_playtime":
            game_id = str(args.get("game_id", "")).strip()
            if game_id:
                games = _load_games()
                for g in games:
                    if str(g.get("id")) == game_id or g.get("slug", "") == game_id:
                        name_ = g.get("name", "?")
                        playtime = g.get("playtime", "?")
                        seconds = g.get("playtimeSeconds", 0) or 0
                        hours = int(seconds // 3600)
                        mins = int((seconds % 3600) // 60)
                        return f"{name_}: {playtime} ({hours}h {mins}m)"
                return f"Game {game_id} not found."
            games = _load_games()
            if not games:
                return "No games to show play time for."
            total_seconds = sum(g.get("playtimeSeconds", 0) or 0 for g in games)
            hours = int(total_seconds // 3600)
            mins = int((total_seconds % 3600) // 60)
            with_playtime = sum(1 for g in games if g.get("playtimeSeconds", 0))
            lines = [
                f"Total: {len(games)} games, {with_playtime} played",
                f"Total play time: {hours}h {mins}m",
            ]
            lines.append("\nTop games:")
            games_with_time = [g for g in games if g.get("playtimeSeconds", 0)]
            if games_with_time:
                games_with_time.sort(key=lambda g: g.get("playtimeSeconds", 0), reverse=True)
                for g in games_with_time[:5]:
                    name_ = g.get("name", "?")
                    playtime = g.get("playtime", "?")
                    lines.append(f"  {name_}: {playtime}")
            return "\n".join(lines)

    except Exception as e:
        return f"[lutris] {e}"

    return f"[lutris] unknown tool: {name}"
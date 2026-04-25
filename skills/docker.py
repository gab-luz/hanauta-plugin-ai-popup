"""Docker skill — list, start, stop, restart containers and tail logs."""
from __future__ import annotations

import subprocess
import json

SKILL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "docker_ps",
            "description": "List running (or all) Docker containers with their status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "all": {
                        "type": "boolean",
                        "description": "If true, include stopped containers too.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "docker_start",
            "description": "Start a stopped Docker container.",
            "parameters": {
                "type": "object",
                "properties": {
                    "container": {"type": "string", "description": "Container name or ID."}
                },
                "required": ["container"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "docker_stop",
            "description": "Stop a running Docker container.",
            "parameters": {
                "type": "object",
                "properties": {
                    "container": {"type": "string", "description": "Container name or ID."}
                },
                "required": ["container"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "docker_restart",
            "description": "Restart a Docker container.",
            "parameters": {
                "type": "object",
                "properties": {
                    "container": {"type": "string", "description": "Container name or ID."}
                },
                "required": ["container"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "docker_logs",
            "description": "Fetch the last N lines of logs from a Docker container.",
            "parameters": {
                "type": "object",
                "properties": {
                    "container": {"type": "string", "description": "Container name or ID."},
                    "lines": {"type": "integer", "description": "Number of tail lines (default 40)."},
                },
                "required": ["container"],
            },
        },
    },
]


def _run(cmd: list[str], timeout: float = 10.0) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    if result.returncode != 0:
        raise RuntimeError(err or out or f"exit {result.returncode}")
    return out or err


def dispatch(name: str, args: dict) -> str:
    if name == "docker_ps":
        cmd = ["docker", "ps", "--format", "table {{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}"]
        if args.get("all"):
            cmd.insert(2, "-a")
        return _run(cmd)

    if name == "docker_start":
        return _run(["docker", "start", args["container"]])

    if name == "docker_stop":
        return _run(["docker", "stop", args["container"]])

    if name == "docker_restart":
        return _run(["docker", "restart", args["container"]])

    if name == "docker_logs":
        lines = int(args.get("lines") or 40)
        return _run(["docker", "logs", "--tail", str(lines), args["container"]], timeout=15.0)

    return f"[docker] unknown tool: {name}"

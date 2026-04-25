"""Hanauta Mail skill — read unread mail and send messages via msmtp/notmuch."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

SKILL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "mail_unread_count",
            "description": "Return the number of unread emails.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mail_list_unread",
            "description": "List unread email subjects, senders, and dates (up to N messages).",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max messages to return (default 10)."}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mail_read",
            "description": "Read the body of an email by its notmuch message ID or thread ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "notmuch message ID (id:...) or thread ID (thread:...)."}
                },
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mail_send",
            "description": "Send an email via msmtp.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address."},
                    "subject": {"type": "string"},
                    "body": {"type": "string", "description": "Plain-text message body."},
                    "from_addr": {"type": "string", "description": "Sender address (optional, uses msmtp default)."},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mail_search",
            "description": "Search emails using a notmuch query string.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "notmuch search query, e.g. 'from:alice subject:invoice'."},
                    "limit": {"type": "integer", "description": "Max results (default 10)."},
                },
                "required": ["query"],
            },
        },
    },
]


def _notmuch(args: list[str], timeout: float = 10.0) -> str:
    result = subprocess.run(
        ["notmuch", *args], capture_output=True, text=True, timeout=timeout, check=False
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "notmuch error").strip())
    return (result.stdout or "").strip()


def dispatch(name: str, args: dict) -> str:
    if name == "mail_unread_count":
        try:
            count = _notmuch(["count", "tag:unread"])
            return f"{count} unread message(s)."
        except Exception as exc:
            return f"[mail] {exc}"

    if name == "mail_list_unread":
        limit = int(args.get("limit") or 10)
        try:
            raw = _notmuch([
                "search", "--format=json", "--limit", str(limit), "tag:unread"
            ])
            threads = json.loads(raw)
            if not threads:
                return "No unread messages."
            lines = []
            for t in threads:
                authors = t.get("authors", "?")
                subject = t.get("subject", "(no subject)")
                date = t.get("date_relative", "")
                tid = t.get("thread", "")
                lines.append(f"[{date}] {authors}: {subject}  (thread:{tid})")
            return "\n".join(lines)
        except Exception as exc:
            return f"[mail] {exc}"

    if name == "mail_read":
        msg_id = str(args["id"]).strip()
        try:
            raw = _notmuch(["show", "--format=json", "--body=true", msg_id])
            data = json.loads(raw)
            # Flatten first message body parts
            parts: list[str] = []

            def _extract(node) -> None:
                if isinstance(node, list):
                    for item in node:
                        _extract(item)
                elif isinstance(node, dict):
                    content = node.get("content", "")
                    if isinstance(content, str) and node.get("content-type", "").startswith("text/plain"):
                        parts.append(content.strip())
                    elif isinstance(content, list):
                        _extract(content)

            _extract(data)
            return "\n\n".join(parts) or "(no plain-text body)"
        except Exception as exc:
            return f"[mail] {exc}"

    if name == "mail_send":
        to = str(args["to"]).strip()
        subject = str(args["subject"]).strip()
        body = str(args["body"]).strip()
        from_addr = str(args.get("from_addr") or "").strip()
        header_from = f"From: {from_addr}\n" if from_addr else ""
        message = (
            f"{header_from}"
            f"To: {to}\n"
            f"Subject: {subject}\n"
            f"Content-Type: text/plain; charset=utf-8\n\n"
            f"{body}\n"
        )
        try:
            cmd = ["msmtp", "-t"]
            result = subprocess.run(
                cmd, input=message, capture_output=True, text=True, timeout=30, check=False
            )
            if result.returncode != 0:
                raise RuntimeError((result.stderr or result.stdout or "msmtp error").strip())
            return f"Email sent to {to}."
        except FileNotFoundError:
            return "[mail] msmtp not found. Install msmtp to send email."
        except Exception as exc:
            return f"[mail] send failed: {exc}"

    if name == "mail_search":
        query = str(args["query"]).strip()
        limit = int(args.get("limit") or 10)
        try:
            raw = _notmuch(["search", "--format=json", "--limit", str(limit), query])
            threads = json.loads(raw)
            if not threads:
                return "No results."
            lines = []
            for t in threads:
                authors = t.get("authors", "?")
                subject = t.get("subject", "(no subject)")
                date = t.get("date_relative", "")
                tid = t.get("thread", "")
                lines.append(f"[{date}] {authors}: {subject}  (thread:{tid})")
            return "\n".join(lines)
        except Exception as exc:
            return f"[mail] {exc}"

    return f"[mail] unknown tool: {name}"

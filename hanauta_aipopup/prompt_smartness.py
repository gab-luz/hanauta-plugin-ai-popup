from __future__ import annotations

import html
import json
import math
import re
import shutil
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


JsonDict = dict[str, object]


def _apply_inline(escaped_text: str) -> str:
    """Apply inline markdown to already-HTML-escaped text: bold, italic, inline code."""
    import re as _re
    t = escaped_text
    # Inline code: `code` (must come before bold/italic to avoid double-processing)
    t = _re.sub(r'`([^`]+)`', r'<code>\1</code>', t)
    # Bold: **text** or __text__ (handle malformed ***text*** too)
    t = _re.sub(r'\*\*\*?([^*<\n]+?)\*\*\*?', r'<strong>\1</strong>', t)
    t = _re.sub(r'__([^_<\n]+?)__', r'<strong>\1</strong>', t)
    # Italic: *text* or _text_ (only single markers remaining)
    t = _re.sub(r'(?<!\*)\*([^*<\n]+?)\*(?!\*)', r'<em>\1</em>', t)
    t = _re.sub(r'(?<!_)_([^_<\n]+?)_(?!_)', r'<em>\1</em>', t)
    # Clean up any leftover bare markers
    t = t.replace('**', '').replace('__', '')
    return t


@dataclass(frozen=True)
class PromptSmartness:
    state_dir: Path
    token_compressor_sample_file: Path
    token_compressor_file: Path
    memory_db_file: Path
    http_post_json: Callable[..., dict[str, object]]
    api_url_from_host: Callable[[str], str]
    load_secret: Callable[[str], str]
    chmod_private: Callable[[Path], None]

    def strip_simple_markdown(self, text: str) -> str:
        """
        Minimal markdown cleanup for speech/UI. We only strip the most common noisy markers
        (bold/italic/code fences) without attempting full markdown parsing.
        """
        s = str(text or "")
        s = s.replace("```", "")
        s = s.replace("`", "")
        # Bold markers (paired first, then leftovers).
        s = re.sub(r"\*\*([^\n]+?)\*\*", r"\1", s)
        s = re.sub(r"__([^\n]+?)__", r"\1", s)
        s = s.replace("**", "").replace("__", "")
        # Leave single '*' unless it looks like a trailing artifact.
        s = re.sub(r"\*{3,}", "", s)
        return s

    def render_llm_text_html(self, text: str) -> str:
        """
        Render assistant text as safe HTML.
        Supports: **bold**, *italic*, # headings, - / * bullet lists,
        double-newline paragraph breaks, inline code `x`, and \n line breaks.
        """
        import re as _re
        raw = str(text or "").strip()
        if not raw:
            return ""

        # Split on double newlines to get paragraphs / blocks
        blocks = _re.split(r"\n{2,}", raw)
        parts: list[str] = []

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            # Heading: # / ## / ###
            heading_match = _re.match(r'^(#{1,3})\s+(.*)', block)
            if heading_match:
                level = min(3, len(heading_match.group(1)))
                content = html.escape(heading_match.group(2).strip())
                content = _apply_inline(content)
                parts.append(f"<h{level}>{content}</h{level}>")
                continue

            # Bullet list: lines starting with - or *
            lines = block.splitlines()
            if all(_re.match(r'^[-*]\s+', l.strip()) for l in lines if l.strip()):
                items = []
                for l in lines:
                    m = _re.match(r'^[-*]\s+(.*)', l.strip())
                    if m:
                        items.append(f"<li>{_apply_inline(html.escape(m.group(1)))}</li>")
                parts.append("<ul>" + "".join(items) + "</ul>")
                continue

            # Numbered list: lines starting with 1. 2. etc.
            if all(_re.match(r'^\d+\.\s+', l.strip()) for l in lines if l.strip()):
                items = []
                for l in lines:
                    m = _re.match(r'^\d+\.\s+(.*)', l.strip())
                    if m:
                        items.append(f"<li>{_apply_inline(html.escape(m.group(1)))}</li>")
                parts.append("<ol>" + "".join(items) + "</ol>")
                continue

            # Regular paragraph — join lines with <br>
            escaped_lines = [html.escape(l) for l in lines]
            joined = "<br>".join(escaped_lines)
            parts.append(f"<p>{_apply_inline(joined)}</p>")

        return "".join(parts)

    def ensure_token_compressor_file(self) -> Path:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        try:
            if self.token_compressor_file.exists():
                return self.token_compressor_file
            if self.token_compressor_sample_file.exists():
                shutil.copy2(self.token_compressor_sample_file, self.token_compressor_file)
                self.chmod_private(self.token_compressor_file)
                return self.token_compressor_file
        except Exception:
            pass
        try:
            self.token_compressor_file.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "collapse_whitespace": True,
                        "filler_words": ["um", "uh", "erm"],
                        "replace_phrases": {"please": ""},
                        "drop_sentences_containing": [],
                        "max_words": 90,
                        "max_chars": 560,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            self.chmod_private(self.token_compressor_file)
        except Exception:
            pass
        return self.token_compressor_file

    def load_token_compressor(self) -> JsonDict:
        self.ensure_token_compressor_file()
        try:
            raw = self.token_compressor_file.read_text(encoding="utf-8")
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def compress_voice_prompt(self, text: str) -> str:
        """
        Compress a voice prompt (typically Whisper transcript) to reduce prompt tokens.
        Intentionally dumb but safe: we escape all user-provided phrases and never compile
        arbitrary regex patterns.
        """
        original = str(text or "").strip()
        if not original:
            return ""
        cfg = self.load_token_compressor()
        s = original

        def _ci_sub(needle: str, repl: str) -> None:
            nonlocal s
            clean = str(needle or "").strip()
            if not clean:
                return
            try:
                s = re.sub(re.escape(clean), str(repl), s, flags=re.IGNORECASE)
            except Exception:
                s = s.replace(clean, str(repl))

        replace_phrases = cfg.get("replace_phrases", {})
        if isinstance(replace_phrases, dict):
            for k, v in replace_phrases.items():
                _ci_sub(str(k), str(v))

        filler = cfg.get("filler_words", [])
        if isinstance(filler, list):
            for word in filler:
                w = str(word or "").strip()
                if not w:
                    continue
                if " " in w:
                    _ci_sub(w, "")
                else:
                    try:
                        s = re.sub(rf"(?i)\b{re.escape(w)}\b", "", s)
                    except Exception:
                        _ci_sub(w, "")

        drop = cfg.get("drop_sentences_containing", [])
        if isinstance(drop, list) and drop:
            try:
                parts = re.split(r"(?<=[\.\!\?])\s+|\n+", s)
            except Exception:
                parts = [s]
            kept: list[str] = []
            for part in parts:
                p = str(part).strip()
                if not p:
                    continue
                low = p.lower()
                if any(str(item).strip().lower() in low for item in drop if str(item).strip()):
                    continue
                kept.append(p)
            if kept:
                s = " ".join(kept)

        if bool(cfg.get("collapse_whitespace", True)):
            s = " ".join(s.split())

        try:
            max_words = int(cfg.get("max_words", 90) or 0)
        except Exception:
            max_words = 90
        if max_words > 0:
            words = s.split()
            if len(words) > max_words:
                s = " ".join(words[-max_words:])

        try:
            max_chars = int(cfg.get("max_chars", 560) or 0)
        except Exception:
            max_chars = 560
        if max_chars > 0 and len(s) > max_chars:
            s = s[-max_chars:].lstrip()

        return s.strip() or original

    def cosine_similarity(self, a: list[float], b: list[float]) -> float:
        if not a or not b:
            return -1.0
        n = min(len(a), len(b))
        dot = 0.0
        sa = 0.0
        sb = 0.0
        for i in range(n):
            x = float(a[i])
            y = float(b[i])
            dot += x * y
            sa += x * x
            sb += y * y
        denom = math.sqrt(sa) * math.sqrt(sb)
        return (dot / denom) if denom > 0 else -1.0

    def fetch_openai_style_embedding(self, host: str, model: str, text: str, api_key: str = "") -> list[float]:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        payload: dict[str, object] = {"model": model.strip(), "input": text}
        response = self.http_post_json(
            f"{self.api_url_from_host(host)}/v1/embeddings",
            payload,
            timeout=60.0,
            headers=headers,
        )
        data = response.get("data", [])
        if not isinstance(data, list) or not data:
            return []
        first = data[0]
        if not isinstance(first, dict):
            return []
        embedding = first.get("embedding", [])
        if not isinstance(embedding, list):
            return []
        out: list[float] = []
        for value in embedding:
            try:
                out.append(float(value))
            except Exception:
                out.append(0.0)
        return out

    def memory_db_init(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS voice_memory ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "role TEXT NOT NULL,"
            "content TEXT NOT NULL,"
            "embedding TEXT NOT NULL,"
            "created_at REAL NOT NULL"
            ")"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_voice_memory_created_at ON voice_memory(created_at)")
        conn.commit()

    def memory_add(self, role: str, content: str, embedding: list[float]) -> None:
        clean = str(content or "").strip()
        if not clean or not embedding:
            return
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.memory_db_file)) as conn:
            self.memory_db_init(conn)
            conn.execute(
                "INSERT INTO voice_memory(role, content, embedding, created_at) VALUES(?,?,?,?)",
                (str(role or "user"), clean[:4000], json.dumps(embedding), float(time.time())),
            )
            try:
                max_rows = 2500
                conn.execute(
                    "DELETE FROM voice_memory WHERE id NOT IN (SELECT id FROM voice_memory ORDER BY id DESC LIMIT ?)",
                    (max_rows,),
                )
            except Exception:
                pass
            conn.commit()

    def memory_recall(self, host: str, model: str, api_key: str, query: str, top_k: int, max_chars: int) -> str:
        q = str(query or "").strip()
        if not q:
            return ""
        query_emb = self.fetch_openai_style_embedding(host, model, q, api_key)
        if not query_emb:
            return ""
        top_k = max(0, min(12, int(top_k)))
        if top_k <= 0:
            return ""
        max_chars = max(200, min(4000, int(max_chars)))

        self.state_dir.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.memory_db_file)) as conn:
            self.memory_db_init(conn)
            rows = conn.execute(
                "SELECT role, content, embedding FROM voice_memory ORDER BY id DESC LIMIT 450"
            ).fetchall()
        scored: list[tuple[float, str, str]] = []
        for role, content, emb_json in rows:
            try:
                emb = json.loads(emb_json)
            except Exception:
                emb = []
            if not isinstance(emb, list):
                continue
            try:
                emb_floats = [float(x) for x in emb]
            except Exception:
                continue
            score = self.cosine_similarity(query_emb, emb_floats)
            if score <= 0:
                continue
            scored.append((score, str(role), str(content)))
        if not scored:
            return ""
        scored.sort(key=lambda t: t[0], reverse=True)

        lines: list[str] = []
        used = 0
        for score, role, content in scored[:top_k]:
            del score
            prefix = "User" if role == "user" else "Assistant"
            snippet = " ".join(str(content).split())
            if len(snippet) > 420:
                snippet = snippet[:420].rstrip() + "..."
            line = f"{prefix}: {snippet}"
            if used + len(line) + 1 > max_chars:
                break
            lines.append(line)
            used += len(line) + 1
        return "\n".join(lines).strip()


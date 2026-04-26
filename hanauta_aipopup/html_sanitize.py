from __future__ import annotations

import html
from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import urlparse


# NOTE: This sanitizer is intentionally small and conservative:
# - keeps basic formatting tags so the app can render HTML message bodies
# - strips script/style/iframe/etc and inline event handlers
# - blocks `javascript:` URLs
# It is not meant to be a fully fledged HTML sanitizer, just a safe-enough guard
# for rendering untrusted content in QTextDocument / QWebEngine.


_STRIP_TAGS = {
    "script",
    "style",
    "iframe",
    "object",
    "embed",
    "link",
    "meta",
}

_ALLOWED_TAGS = {
    "a",
    "b",
    "blockquote",
    "br",
    "button",
    "code",
    "div",
    "em",
    "hr",
    "i",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "s",
    "small",
    "span",
    "strong",
    "sub",
    "sup",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "u",
    "ul",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
}

_GLOBAL_ALLOWED_ATTRS = {
    "title",
}

_TAG_ALLOWED_ATTRS: dict[str, set[str]] = {
    "a": {"href", "title"},
    "button": {"class", "data-cmd", "data-card-id", "type", "style"},
    "img": {"src", "alt", "title", "width", "height"},
    "td": {"colspan", "rowspan", "align", "valign"},
    "th": {"colspan", "rowspan", "align", "valign"},
    "table": {"cellspacing", "cellpadding", "border", "width"},
}

_ALLOWED_LINK_SCHEMES = {"", "http", "https", "mailto", "file", "qrc", "hanauta-audio"}
_ALLOWED_IMAGE_SCHEMES = {"", "http", "https", "file", "qrc", "data"}


def _is_safe_href(value: str) -> bool:
    raw = (value or "").strip()
    if not raw:
        return False
    try:
        parsed = urlparse(raw)
    except Exception:
        return False
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_LINK_SCHEMES:
        return False
    if scheme == "javascript":
        return False
    return True


def _is_safe_img_src(value: str) -> bool:
    raw = (value or "").strip()
    if not raw:
        return False
    try:
        parsed = urlparse(raw)
    except Exception:
        return False
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_IMAGE_SCHEMES:
        return False
    if scheme == "javascript":
        return False
    if scheme == "data":
        lowered = raw.lower()
        return lowered.startswith("data:image/")
    return True


class _SafeHtml(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._out: list[str] = []
        self._open: list[str] = []
        self._strip_depth = 0

    def get_html(self) -> str:
        while self._open:
            self._out.append(f"</{self._open.pop()}>")
        return "".join(self._out).strip()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:  # type: ignore[override]
        t = (tag or "").lower()
        if t in _STRIP_TAGS:
            self._strip_depth += 1
            return
        if self._strip_depth:
            return
        if t not in _ALLOWED_TAGS:
            return
        rendered = self._render_attrs(t, attrs)
        self._out.append(f"<{t}{rendered}>")
        if t not in {"br", "img", "hr"}:
            self._open.append(t)

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        t = (tag or "").lower()
        if t in _STRIP_TAGS:
            if self._strip_depth:
                self._strip_depth -= 1
            return
        if self._strip_depth:
            return
        if t not in _ALLOWED_TAGS:
            return
        for idx in range(len(self._open) - 1, -1, -1):
            if self._open[idx] == t:
                while len(self._open) > idx:
                    closing = self._open.pop()
                    self._out.append(f"</{closing}>")
                return

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:  # type: ignore[override]
        t = (tag or "").lower()
        if t in _STRIP_TAGS:
            return
        if self._strip_depth:
            return
        if t not in _ALLOWED_TAGS:
            return
        rendered = self._render_attrs(t, attrs)
        self._out.append(f"<{t}{rendered} />")

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if self._strip_depth:
            return
        if not data:
            return
        self._out.append(html.escape(data, quote=False))

    def handle_entityref(self, name: str) -> None:  # type: ignore[override]
        if self._strip_depth:
            return
        if not name:
            return
        self._out.append(f"&{name};")

    def handle_charref(self, name: str) -> None:  # type: ignore[override]
        if self._strip_depth:
            return
        if not name:
            return
        self._out.append(f"&#{name};")

    def _render_attrs(self, tag: str, attrs: Iterable[tuple[str, str | None]]) -> str:
        allowed = set(_GLOBAL_ALLOWED_ATTRS)
        allowed.update(_TAG_ALLOWED_ATTRS.get(tag, set()))
        parts: list[str] = []
        for key, value in attrs:
            k = (key or "").strip().lower()
            if not k:
                continue
            if k.startswith("on"):
                continue
            if k not in allowed:
                continue
            v = (value or "").strip()
            if not v:
                continue
            if tag == "a" and k == "href":
                if not _is_safe_href(v):
                    continue
            if tag == "img" and k == "src":
                if not _is_safe_img_src(v):
                    continue
            parts.append(f' {k}="{html.escape(v, quote=True)}"')
        return "".join(parts)


def sanitize_message_html(text: str, *, allow_html: bool = True) -> str:
    raw = str(text or "")
    if not raw.strip():
        return ""
    if not allow_html:
        return f"<p>{html.escape(raw)}</p>"
    parser = _SafeHtml()
    try:
        parser.feed(raw)
        parser.close()
    except Exception:
        return f"<p>{html.escape(raw)}</p>"
    return parser.get_html()


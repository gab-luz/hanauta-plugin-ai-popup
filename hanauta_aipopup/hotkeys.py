"""Global capture hotkeys on X11, with no third-party dependency.

Uses ``libX11`` through :mod:`ctypes` so the popup can toggle camera/screen
sharing while another window (a game, a browser) has focus. Everything is
best-effort: if there is no X display, no ``libX11``, or another client already
owns the combination, the popup simply runs without hotkeys.

Wayland is not supported by ``XGrabKey``; the caller reports that instead of
failing silently.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os

from PyQt6.QtCore import QObject, QSocketNotifier, pyqtSignal

_KEY_PRESS = 2
_GRAB_MODE_ASYNC = 1
_LOCK_MASK = 2
_SHIFT_MASK = 1
_CONTROL_MASK = 4
_MOD1_MASK = 8
_MOD4_MASK = 64
_NUM_LOCK_MASK = 16
_IGNORED_MASKS = _LOCK_MASK | _NUM_LOCK_MASK

_MODIFIERS = {
    "ctrl": _CONTROL_MASK,
    "control": _CONTROL_MASK,
    "alt": _MOD1_MASK,
    "shift": _SHIFT_MASK,
    "super": _MOD4_MASK,
    "meta": _MOD4_MASK,
    "mod4": _MOD4_MASK,
}

# Offsets inside the XKeyEvent struct (x86_64 X11 layout).
_OFFSET_STATE = 80
_OFFSET_KEYCODE = 84
_EVENT_BUFFER = 192

# Offsets inside XErrorEvent, and the codes we care about.
_OFFSET_ERROR_CODE = 32
_OFFSET_REQUEST_CODE = 33
_BAD_ACCESS = 10
_X_GRAB_KEY_REQUEST = 33

# X errors are asynchronous: record them so a failed grab can be attributed.
_ERROR_SINK: list[tuple[int, int]] = []
_CONFLICTS: dict[str, str] = {}


def record_conflicts(conflicts: dict[str, str]) -> None:
    """Remember which bindings the last attempt could not grab (for the UI)."""
    global _CONFLICTS
    _CONFLICTS = dict(conflicts)


def known_conflicts() -> dict[str, str]:
    """Return ``action -> binding`` for hotkeys another client already owns."""
    return dict(_CONFLICTS)


def describe_conflicts(conflicts: dict[str, str]) -> str:
    """Human-readable conflict summary (empty string when there is none)."""
    if not conflicts:
        return ""
    parts = [f"{action} ({spec})" for action, spec in sorted(conflicts.items())]
    return "Hotkey already in use by another application: " + ", ".join(parts)


def parse_binding(binding: str) -> tuple[int, str] | None:
    """Parse ``"<ctrl>+<alt>+c"`` into ``(modifier_mask, key_name)``."""
    raw = str(binding or "").strip().lower().replace("<", "").replace(">", "")
    tokens = [token for token in raw.replace("+", " ").split() if token]
    mask = 0
    key = ""
    for token in tokens:
        if token in _MODIFIERS:
            mask |= _MODIFIERS[token]
        else:
            key = token
    if not key or len(key) > 12:
        return None
    return mask, key


class GlobalHotkeys(QObject):
    """Grabs key combinations and emits :attr:`triggered` with the action name."""

    triggered = pyqtSignal(str)

    def __init__(self, bindings: dict[str, str], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._bindings = dict(bindings)
        self._lib: ctypes.CDLL | None = None
        self._display: int | None = None
        self._notifier: QSocketNotifier | None = None
        self._grabs: dict[tuple[int, int], str] = {}
        self._error_handler = None
        self.conflicts: dict[str, str] = {}

    @property
    def bindings(self) -> dict[str, str]:
        return dict(self._bindings)

    def start(self) -> tuple[bool, str]:
        if not self._bindings:
            return False, "no capture hotkeys configured"
        if not os.environ.get("DISPLAY", "").strip():
            return False, "no X display (global hotkeys need X11; Wayland is unsupported)"
        try:
            lib = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
        except OSError as exc:
            return False, f"libX11 unavailable: {exc}"

        lib.XOpenDisplay.restype = ctypes.c_void_p
        lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        lib.XStringToKeysym.restype = ctypes.c_ulong
        lib.XStringToKeysym.argtypes = [ctypes.c_char_p]
        lib.XKeysymToKeycode.restype = ctypes.c_ubyte
        lib.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        lib.XDefaultRootWindow.restype = ctypes.c_ulong
        lib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        lib.XGrabKey.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ulong,
            ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ]
        lib.XNextEvent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        lib.XPending.argtypes = [ctypes.c_void_p]
        lib.XPending.restype = ctypes.c_int
        lib.XConnectionNumber.argtypes = [ctypes.c_void_p]
        lib.XConnectionNumber.restype = ctypes.c_int
        lib.XUngrabKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ulong]
        lib.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]

        display = lib.XOpenDisplay(None)
        if not display:
            return False, "could not open the X display"
        # Grab conflicts raise BadAccess. The default handler would terminate the
        # app, so swallow the error but record it, which is how a conflicting
        # hotkey is attributed to the binding that lost.
        def _on_x_error(_dpy, event) -> int:
            try:
                codes = ctypes.cast(event, ctypes.POINTER(ctypes.c_ubyte))
                _ERROR_SINK.append((int(codes[_OFFSET_REQUEST_CODE]), int(codes[_OFFSET_ERROR_CODE])))
            except Exception:
                pass
            return 0

        self._error_handler = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)(_on_x_error)
        lib.XSetErrorHandler.argtypes = [ctypes.c_void_p]
        lib.XSetErrorHandler(self._error_handler)

        root = lib.XDefaultRootWindow(display)
        grabbed = 0
        conflicts: dict[str, str] = {}
        skipped: list[str] = []
        for action, spec in self._bindings.items():
            parsed = parse_binding(spec)
            if parsed is None:
                skipped.append(spec)
                continue
            mask, key_name = parsed
            keysym = lib.XStringToKeysym(key_name.encode("utf-8"))
            if not keysym:
                skipped.append(spec)
                continue
            keycode = lib.XKeysymToKeycode(display, keysym)
            if not keycode:
                skipped.append(spec)
                continue
            _ERROR_SINK.clear()
            for extra in (0, _LOCK_MASK, _NUM_LOCK_MASK, _LOCK_MASK | _NUM_LOCK_MASK):
                lib.XGrabKey(display, keycode, mask | extra, root, False, _GRAB_MODE_ASYNC, _GRAB_MODE_ASYNC)
            # XSync flushes and processes the errors, so a conflict is visible here.
            lib.XSync(display, False)
            if any(request == _X_GRAB_KEY_REQUEST and code == _BAD_ACCESS for request, code in _ERROR_SINK):
                conflicts[action] = spec
                continue
            self._grabs[(int(keycode), int(mask))] = action
            grabbed += 1

        self._lib = lib
        self._display = display
        self._notifier = QSocketNotifier(int(lib.XConnectionNumber(display)), QSocketNotifier.Type.Read, self)
        self._notifier.activated.connect(self._drain)

        record_conflicts(conflicts)
        self.conflicts = dict(conflicts)
        if not grabbed:
            detail = describe_conflicts(conflicts)
            if not detail:
                detail = f"could not bind {', '.join(skipped)}" if skipped else "no hotkey could be bound"
            return False, detail
        message = f"{grabbed} capture hotkey(s) active"
        if conflicts:
            message += "; " + describe_conflicts(conflicts)
        return True, message

    def stop(self) -> None:
        if self._lib is None or self._display is None:
            return
        try:
            root = self._lib.XDefaultRootWindow(self._display)
            for keycode, mask in self._grabs:
                self._lib.XUngrabKey(self._display, keycode, mask, root)
            self._lib.XSync(self._display, False)
        except Exception:
            pass
        if self._notifier is not None:
            self._notifier.setEnabled(False)
            self._notifier = None
        self._grabs.clear()
        self._lib = None
        self._display = None

    def _drain(self) -> None:
        if self._lib is None or self._display is None:
            return
        buffer = ctypes.create_string_buffer(_EVENT_BUFFER)
        while self._lib.XPending(self._display) > 0:
            self._lib.XNextEvent(self._display, buffer)
            if ctypes.c_int.from_buffer(buffer, 0).value != _KEY_PRESS:
                continue
            state = ctypes.c_uint.from_buffer(buffer, _OFFSET_STATE).value & ~_IGNORED_MASKS
            keycode = ctypes.c_uint.from_buffer(buffer, _OFFSET_KEYCODE).value
            action = self._grabs.get((int(keycode), int(state)))
            if action:
                self.triggered.emit(action)


__all__ = [
    "GlobalHotkeys",
    "describe_conflicts",
    "known_conflicts",
    "parse_binding",
    "record_conflicts",
]

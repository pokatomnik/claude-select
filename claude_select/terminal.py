"""Low-level terminal handling: raw mode, key reads and screen drawing.

This is the only module besides :mod:`claude_select.picker` that talks to the
terminal. Keep the I/O surface small so everything else stays testable.
"""

from __future__ import annotations

import contextlib
import os
import select
from typing import IO, Iterator, List

from .keys import Key, decode_key, decode_windows_key

_ESC = b"\x1b"
_ESCAPE_TAIL_BYTES = 6
_ESCAPE_TIMEOUT = 0.05


def is_interactive(stream: IO[str]) -> bool:
    """Return ``True`` when ``stream`` is attached to a terminal."""
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError, OSError):
        return False


@contextlib.contextmanager
def raw_mode(fd: int) -> Iterator[None]:
    """Put the terminal into cbreak mode for the duration of the block."""
    if os.name == "nt":  # pragma: no cover - platform specific
        yield
        return

    import termios
    import tty

    previous = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    try:
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)


def read_key(fd: int) -> Key:
    """Block until a key is pressed and decode it."""
    if os.name == "nt":  # pragma: no cover - platform specific
        return _read_key_windows()

    data = os.read(fd, 1)
    if not data:
        return Key.CANCEL
    if data == _ESC:
        data += _read_escape_tail(fd)
    return decode_key(data)


def _read_escape_tail(fd: int) -> bytes:  # pragma: no cover - terminal I/O
    tail = b""
    for _ in range(_ESCAPE_TAIL_BYTES):
        ready, _, _ = select.select([fd], [], [], _ESCAPE_TIMEOUT)
        if not ready:
            break
        chunk = os.read(fd, 1)
        if not chunk:
            break
        tail += chunk
        if decode_key(_ESC + tail) is not Key.OTHER:
            break
    return tail


def _read_key_windows() -> Key:  # pragma: no cover - platform specific
    import msvcrt

    first = msvcrt.getwch()
    if first in ("\x00", "\xe0"):
        return decode_windows_key(first, msvcrt.getwch())
    return decode_windows_key(first)


class Screen:
    """Redraw a fixed-size block of lines that starts at the cursor."""

    def __init__(self, stream: IO[str]) -> None:
        self._stream = stream
        self._lines = 0

    def hide_cursor(self) -> None:
        self._write("\x1b[?25l")

    def show_cursor(self) -> None:
        self._write("\x1b[?25h")

    def draw(self, lines: List[str]) -> None:
        if self._lines:
            self._write("\x1b[" + str(self._lines) + "A")
        for line in lines:
            self._write("\x1b[2K" + line + "\n")
        self._lines = len(lines)

    def clear(self) -> None:
        if not self._lines:
            return
        self._write("\x1b[" + str(self._lines) + "A")
        for _ in range(self._lines):
            self._write("\x1b[2K\n")
        self._write("\x1b[" + str(self._lines) + "A")
        self._lines = 0

    def _write(self, text: str) -> None:
        self._stream.write(text)
        self._stream.flush()

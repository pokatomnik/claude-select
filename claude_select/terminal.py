"""Low-level terminal handling: raw mode, key reads and screen drawing.

This is the only module besides :mod:`claude_select.picker` that talks to the
terminal. Keep the I/O surface small so everything else stays testable.
"""

from __future__ import annotations

import contextlib
import os
import select
from typing import IO, Any, Callable, Iterator, List, NamedTuple, Optional, Tuple

from .keys import Key, decode_key, decode_windows_key

_ESC = b"\x1b"
_ESCAPE_TAIL_BYTES = 6
_ESCAPE_TIMEOUT = 0.05

_FALLBACK_COLUMNS = 80
_FALLBACK_ROWS = 24

# Line-input/echo bits belong to the input console mode, VT processing to the
# output mode; they share the value 0x0004 but are set on different handles.
_ENABLE_LINE_INPUT = 0x0002
_ENABLE_ECHO_INPUT = 0x0004
_ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004


def terminal_size(
    stream: IO[str],
    size_of: Optional[Callable[[int], Any]] = None,
) -> Tuple[int, int]:
    """Return ``(columns, rows)`` of the terminal behind ``stream``."""
    getter = os.get_terminal_size if size_of is None else size_of
    try:
        size = getter(stream.fileno())
    except (AttributeError, ValueError, OSError):
        return (_FALLBACK_COLUMNS, _FALLBACK_ROWS)
    return (int(size.columns), int(size.lines))


def is_interactive(stream: IO[str]) -> bool:
    """Return ``True`` when ``stream`` is attached to a terminal."""
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError, OSError):
        return False


class TermiosOps(NamedTuple):
    """Terminal calls used by :func:`raw_mode`, replaceable in tests."""

    get_attrs: Callable[[int], Any]
    set_cbreak: Callable[[int], None]
    restore_attrs: Callable[[int, Any], None]


def _posix_ops() -> TermiosOps:  # pragma: no cover - platform specific
    import termios
    import tty

    return TermiosOps(
        get_attrs=termios.tcgetattr,
        set_cbreak=tty.setcbreak,
        restore_attrs=lambda fd, attrs: termios.tcsetattr(
            fd, termios.TCSADRAIN, attrs
        ),
    )


class WindowsConsoleOps(NamedTuple):
    """Console-mode calls used by :func:`raw_mode` on Windows."""

    get_mode: Callable[[int], int]
    set_mode: Callable[[int, int], None]


def _windows_console_ops() -> WindowsConsoleOps:  # pragma: no cover
    import ctypes
    import msvcrt

    kernel32 = ctypes.windll.kernel32

    def get_mode(fd: int) -> int:
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(
            msvcrt.get_osfhandle(fd), ctypes.byref(mode)
        ):
            raise OSError("GetConsoleMode failed")
        return int(mode.value)

    def set_mode(fd: int, mode: int) -> None:
        if not kernel32.SetConsoleMode(msvcrt.get_osfhandle(fd), mode):
            raise OSError("SetConsoleMode failed")

    return WindowsConsoleOps(get_mode, set_mode)


@contextlib.contextmanager
def windows_raw_mode(
    input_fd: int,
    input_ops: Optional[WindowsConsoleOps] = None,
    output_fd: Optional[int] = None,
    output_ops: Optional[WindowsConsoleOps] = None,
) -> Iterator[None]:
    """Disable line input and echo, and turn on ANSI escapes, on Windows.

    ``input_fd`` and ``input_ops`` control the console input mode (no line
    buffering, no echo); ``output_fd`` and ``output_ops`` control the output
    mode, where the VT-processing bit makes ANSI escapes work. Passing
    ``output_fd=None`` leaves the output mode alone.
    """
    stdin = _windows_console_ops() if input_ops is None else input_ops
    previous_input = stdin.get_mode(input_fd)

    previous_output = None
    stdout = None
    if output_fd is not None:
        stdout = _windows_console_ops() if output_ops is None else output_ops
        previous_output = stdout.get_mode(output_fd)

    try:
        stdin.set_mode(
            input_fd, previous_input & ~(_ENABLE_LINE_INPUT | _ENABLE_ECHO_INPUT)
        )
        if stdout is not None and previous_output is not None:
            stdout.set_mode(
                output_fd, previous_output | _ENABLE_VIRTUAL_TERMINAL_PROCESSING
            )
        yield
    finally:
        stdin.set_mode(input_fd, previous_input)
        if stdout is not None and previous_output is not None:
            stdout.set_mode(output_fd, previous_output)


@contextlib.contextmanager
def raw_mode(
    fd: int,
    *,
    ops: Optional[TermiosOps] = None,
    windows_ops: Optional[WindowsConsoleOps] = None,
    output_fd: Optional[int] = None,
    windows_output_ops: Optional[WindowsConsoleOps] = None,
) -> Iterator[None]:
    """Put the terminal into cbreak mode for the duration of the block."""
    if os.name == "nt":  # pragma: no cover - platform specific
        with windows_raw_mode(
            fd, windows_ops, output_fd=output_fd, output_ops=windows_output_ops
        ):
            yield
        return

    active = _posix_ops() if ops is None else ops
    previous = active.get_attrs(fd)
    try:
        active.set_cbreak(fd)
        yield
    finally:
        active.restore_attrs(fd, previous)


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

"""Key decoding for the interactive picker (pure functions, no I/O)."""

from __future__ import annotations

from enum import Enum
from typing import Dict, Optional


class Key(Enum):
    """A logical key press understood by the picker."""

    UP = "up"
    DOWN = "down"
    HOME = "home"
    END = "end"
    CONFIRM = "confirm"
    CANCEL = "cancel"
    OTHER = "other"


_SEQUENCES: Dict[bytes, Key] = {
    b"\r": Key.CONFIRM,
    b"\n": Key.CONFIRM,
    b"\x1b": Key.CANCEL,
    b"\x03": Key.CANCEL,
    b"q": Key.CANCEL,
    b"Q": Key.CANCEL,
    b"j": Key.DOWN,
    b"k": Key.UP,
    b"g": Key.HOME,
    b"G": Key.END,
    b"\x1b[A": Key.UP,
    b"\x1bOA": Key.UP,
    b"\x1b[B": Key.DOWN,
    b"\x1bOB": Key.DOWN,
    b"\x1b[H": Key.HOME,
    b"\x1bOH": Key.HOME,
    b"\x1b[1~": Key.HOME,
    b"\x1b[7~": Key.HOME,
    b"\x1b[F": Key.END,
    b"\x1bOF": Key.END,
    b"\x1b[4~": Key.END,
    b"\x1b[8~": Key.END,
}

_WINDOWS_SIMPLE: Dict[str, Key] = {
    "\r": Key.CONFIRM,
    "\n": Key.CONFIRM,
    "\x1b": Key.CANCEL,
    "\x03": Key.CANCEL,
    "q": Key.CANCEL,
    "Q": Key.CANCEL,
    "j": Key.DOWN,
    "k": Key.UP,
    "g": Key.HOME,
    "G": Key.END,
}

_WINDOWS_SPECIAL: Dict[str, Key] = {
    "H": Key.UP,
    "P": Key.DOWN,
    "G": Key.HOME,
    "O": Key.END,
}


def decode_key(data: bytes) -> Key:
    """Map raw POSIX terminal bytes to a :class:`Key`.

    Unknown sequences return :attr:`Key.OTHER`, which the picker ignores.
    """
    return _SEQUENCES.get(data, Key.OTHER)


def decode_windows_key(first: str, second: Optional[str] = None) -> Key:
    """Map ``msvcrt.getwch()`` output to a :class:`Key`.

    ``second`` is only provided for the ``\\x00``/``\\xe0`` prefixed special
    keys emitted by the Windows console.
    """
    if second is not None:
        return _WINDOWS_SPECIAL.get(second, Key.OTHER)
    return _WINDOWS_SIMPLE.get(first, Key.OTHER)

"""Interactive model picker.

:class:`PickerState` is a pure state machine (no I/O) that is unit-tested.
:func:`pick` adds the thin terminal loop around it.
"""

from __future__ import annotations

import sys
from typing import IO, List, Optional, Sequence

from .errors import TerminalError
from .keys import Key
from .terminal import Screen, is_interactive, raw_mode, read_key

DEFAULT_MAX_VISIBLE = 12

_SELECTED_MARKER = "> "
_UNSELECTED_MARKER = "  "


class PickerState:
    """Cursor and viewport state for a list of labels."""

    def __init__(
        self,
        items: Sequence[str],
        max_visible: int = DEFAULT_MAX_VISIBLE,
    ) -> None:
        if not items:
            raise ValueError("PickerState requires at least one item")
        if max_visible < 1:
            raise ValueError("max_visible must be positive")
        self._items = list(items)
        self._max_visible = max_visible
        self.index = 0
        self.offset = 0

    @property
    def items(self) -> List[str]:
        return list(self._items)

    @property
    def max_visible(self) -> int:
        return self._max_visible

    @property
    def selected(self) -> str:
        return self._items[self.index]

    def move(self, delta: int) -> None:
        """Move the cursor by ``delta`` items, clamping at both ends."""
        self._set_index(self.index + delta)

    def go_home(self) -> None:
        self._set_index(0)

    def go_end(self) -> None:
        self._set_index(len(self._items) - 1)

    def handle_key(self, key: Key) -> bool:
        """Apply a navigation key.

        Returns ``True`` when the screen needs to be redrawn; confirm/cancel
        keys are handled by the caller.
        """
        if key is Key.UP:
            self.move(-1)
        elif key is Key.DOWN:
            self.move(1)
        elif key is Key.HOME:
            self.go_home()
        elif key is Key.END:
            self.go_end()
        else:
            return False
        return True

    def render_lines(self) -> List[str]:
        """Return the visible window, with a marker on the selected row."""
        end = min(self.offset + self._max_visible, len(self._items))
        lines = []
        for position in range(self.offset, end):
            marker = _SELECTED_MARKER if position == self.index else _UNSELECTED_MARKER
            lines.append(marker + self._items[position])
        return lines

    def _set_index(self, target: int) -> None:
        self.index = max(0, min(target, len(self._items) - 1))
        if self.index < self.offset:
            self.offset = self.index
        elif self.index >= self.offset + self._max_visible:
            self.offset = self.index - self._max_visible + 1


def pick(
    items: Sequence[str],
    *,
    input_stream: Optional[IO[str]] = None,
    output_stream: Optional[IO[str]] = None,
    max_visible: int = DEFAULT_MAX_VISIBLE,
) -> Optional[int]:
    """Show an arrow-key picker.

    Returns the index of the confirmed item, or ``None`` when the user
    cancels (``Esc``, ``q`` or ``Ctrl-C``).

    Raises:
        TerminalError: when either stream is not a terminal.
        ValueError: when ``items`` is empty.
    """
    labels = list(items)
    if not labels:
        raise ValueError("pick() requires at least one item")

    source = sys.stdin if input_stream is None else input_stream
    sink = sys.stdout if output_stream is None else output_stream

    if not is_interactive(source) or not is_interactive(sink):
        raise TerminalError(
            "Interactive model selection needs a terminal. Run claude-select "
            "directly in your shell."
        )

    state = PickerState(labels, max_visible=max_visible)
    screen = Screen(sink)
    fd = source.fileno()

    screen.hide_cursor()
    try:
        with raw_mode(fd):
            screen.draw(state.render_lines())
            while True:
                key = read_key(fd)
                if key is Key.CONFIRM:
                    screen.clear()
                    sink.write("Selected: " + labels[state.index] + "\n")
                    sink.flush()
                    return state.index
                if key is Key.CANCEL:
                    screen.clear()
                    return None
                if state.handle_key(key):
                    screen.draw(state.render_lines())
    except KeyboardInterrupt:
        screen.clear()
        return None
    finally:
        screen.show_cursor()

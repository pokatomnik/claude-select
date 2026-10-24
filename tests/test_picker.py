import io
import unittest
from typing import List

from claude_select.errors import TerminalError
from claude_select.keys import Key, decode_key, decode_windows_key
from claude_select.picker import (
    MAX_LINE_WIDTH,
    PickerState,
    fit_line,
    pick,
    visible_rows,
)


class _FakeTty:
    def __init__(self, fail_first_write: bool = False) -> None:
        self.writes: List[str] = []
        self._fail_first_write = fail_first_write

    def isatty(self) -> bool:
        return True

    def fileno(self) -> int:
        return 0

    def write(self, text: str) -> int:
        self.writes.append(text)
        if self._fail_first_write and len(self.writes) == 1:
            raise OSError("write failed")
        return len(text)

    def flush(self) -> None:
        pass


class DecodeKeyTests(unittest.TestCase):
    def test_arrows(self) -> None:
        self.assertIs(Key.UP, decode_key(b"\x1b[A"))
        self.assertIs(Key.DOWN, decode_key(b"\x1b[B"))
        self.assertIs(Key.UP, decode_key(b"\x1bOA"))
        self.assertIs(Key.DOWN, decode_key(b"\x1bOB"))

    def test_home_and_end(self) -> None:
        self.assertIs(Key.HOME, decode_key(b"\x1b[H"))
        self.assertIs(Key.END, decode_key(b"\x1b[F"))
        self.assertIs(Key.HOME, decode_key(b"g"))
        self.assertIs(Key.END, decode_key(b"G"))

    def test_vim_keys(self) -> None:
        self.assertIs(Key.UP, decode_key(b"k"))
        self.assertIs(Key.DOWN, decode_key(b"j"))

    def test_confirm(self) -> None:
        self.assertIs(Key.CONFIRM, decode_key(b"\r"))
        self.assertIs(Key.CONFIRM, decode_key(b"\n"))

    def test_cancel(self) -> None:
        self.assertIs(Key.CANCEL, decode_key(b"\x1b"))
        self.assertIs(Key.CANCEL, decode_key(b"\x03"))
        self.assertIs(Key.CANCEL, decode_key(b"q"))

    def test_unknown(self) -> None:
        self.assertIs(Key.OTHER, decode_key(b"z"))
        self.assertIs(Key.OTHER, decode_key(b"\x1b[Z"))


class DecodeWindowsKeyTests(unittest.TestCase):
    def test_special_keys(self) -> None:
        self.assertIs(Key.UP, decode_windows_key("\xe0", "H"))
        self.assertIs(Key.DOWN, decode_windows_key("\xe0", "P"))
        self.assertIs(Key.HOME, decode_windows_key("\xe0", "G"))
        self.assertIs(Key.END, decode_windows_key("\xe0", "O"))

    def test_simple_keys(self) -> None:
        self.assertIs(Key.CONFIRM, decode_windows_key("\r"))
        self.assertIs(Key.CANCEL, decode_windows_key("\x1b"))
        self.assertIs(Key.CANCEL, decode_windows_key("q"))
        self.assertIs(Key.UP, decode_windows_key("k"))
        self.assertIs(Key.DOWN, decode_windows_key("j"))
        self.assertIs(Key.OTHER, decode_windows_key("z"))

    def test_unknown_special_key(self) -> None:
        self.assertIs(Key.OTHER, decode_windows_key("\xe0", "Z"))


class PickerStateTests(unittest.TestCase):
    def test_initial_state(self) -> None:
        state = PickerState(["a", "b", "c"], max_visible=5)
        self.assertEqual(0, state.index)
        self.assertEqual(0, state.offset)
        self.assertEqual("a", state.selected)
        self.assertEqual(["> a", "  b", "  c"], state.render_lines())

    def test_moves_down_and_clamps(self) -> None:
        state = PickerState(["a", "b", "c"])
        state.move(1)
        self.assertEqual(1, state.index)
        self.assertEqual("b", state.selected)
        state.move(100)
        self.assertEqual(2, state.index)
        self.assertEqual(["  a", "  b", "> c"], state.render_lines())

    def test_moves_up_and_clamps(self) -> None:
        state = PickerState(["a", "b", "c"])
        state.move(100)
        state.move(-1)
        self.assertEqual(1, state.index)
        state.move(-100)
        self.assertEqual(0, state.index)
        self.assertEqual(0, state.offset)

    def test_scrolls_viewport(self) -> None:
        state = PickerState([str(i) for i in range(20)], max_visible=5)
        state.move(10)
        self.assertEqual(10, state.index)
        self.assertEqual(6, state.offset)
        self.assertEqual(
            ["  6", "  7", "  8", "  9", "> 10"],
            state.render_lines(),
        )

    def test_scrolls_back_up(self) -> None:
        state = PickerState([str(i) for i in range(20)], max_visible=5)
        state.move(19)
        self.assertEqual(15, state.offset)
        state.move(-10)
        self.assertEqual(9, state.index)
        self.assertEqual(9, state.offset)

    def test_go_home_and_end(self) -> None:
        state = PickerState([str(i) for i in range(20)], max_visible=5)
        state.go_end()
        self.assertEqual(19, state.index)
        self.assertEqual(15, state.offset)
        state.go_home()
        self.assertEqual(0, state.index)
        self.assertEqual(0, state.offset)

    def test_handle_key_redraw_flags(self) -> None:
        state = PickerState(["a", "b"])
        self.assertTrue(state.handle_key(Key.DOWN))
        self.assertTrue(state.handle_key(Key.UP))
        self.assertTrue(state.handle_key(Key.HOME))
        self.assertTrue(state.handle_key(Key.END))
        self.assertFalse(state.handle_key(Key.CONFIRM))
        self.assertFalse(state.handle_key(Key.CANCEL))
        self.assertFalse(state.handle_key(Key.OTHER))

    def test_rejects_empty_items(self) -> None:
        with self.assertRaises(ValueError):
            PickerState([])

    def test_rejects_bad_window_size(self) -> None:
        with self.assertRaises(ValueError):
            PickerState(["a"], max_visible=0)

    def test_items_returns_copy(self) -> None:
        state = PickerState(["a"])
        state.items.append("b")
        self.assertEqual(["a"], state.items)


class VisibleRowsTests(unittest.TestCase):
    def test_keeps_small_windows(self) -> None:
        self.assertEqual(12, visible_rows(12, 40))

    def test_reserves_a_row_for_the_header_and_the_cursor(self) -> None:
        self.assertEqual(8, visible_rows(12, 10))

    def test_never_goes_below_one(self) -> None:
        self.assertEqual(1, visible_rows(12, 2))
        self.assertEqual(1, visible_rows(12, 1))
        self.assertEqual(1, visible_rows(12, 0))


class FitLineTests(unittest.TestCase):
    def test_short_line_is_unchanged(self) -> None:
        self.assertEqual("> my-model", fit_line("> my-model"))

    def test_line_at_the_limit_is_unchanged(self) -> None:
        line = "x" * MAX_LINE_WIDTH
        self.assertEqual(line, fit_line(line))

    def test_long_line_is_truncated_with_an_ellipsis(self) -> None:
        line = "x" * (MAX_LINE_WIDTH + 50)
        fitted = fit_line(line)
        self.assertEqual(MAX_LINE_WIDTH, len(fitted))
        self.assertTrue(fitted.endswith("..."))
        self.assertTrue(line.startswith(fitted[:-3]))

    def test_custom_width(self) -> None:
        self.assertEqual("abcd...", fit_line("abcdefghij", width=7))


class PickerRenderTests(unittest.TestCase):
    def test_render_caps_long_labels(self) -> None:
        state = PickerState(["y" * (MAX_LINE_WIDTH * 2)])
        line = state.render_lines()[0]
        self.assertEqual(MAX_LINE_WIDTH, len(line))
        self.assertTrue(line.startswith("> "))


class PickGuardTests(unittest.TestCase):
    def test_requires_terminal(self) -> None:
        with self.assertRaises(TerminalError):
            pick(
                ["a"],
                input_stream=io.StringIO(),
                output_stream=io.StringIO(),
            )

    def test_requires_items(self) -> None:
        with self.assertRaises(ValueError):
            pick([], input_stream=io.StringIO(), output_stream=io.StringIO())

    def test_cursor_is_shown_again_when_hiding_fails(self) -> None:
        sink = _FakeTty(fail_first_write=True)
        with self.assertRaises(OSError):
            pick(["a"], input_stream=_FakeTty(), output_stream=sink)
        self.assertEqual(["\x1b[?25l", "\x1b[?25h"], sink.writes)


if __name__ == "__main__":
    unittest.main()

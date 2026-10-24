import unittest
from typing import Any, List, NamedTuple, Tuple

from claude_select.terminal import (
    TermiosOps,
    WindowsConsoleOps,
    raw_mode,
    terminal_size,
    windows_raw_mode,
)


class _Size(NamedTuple):
    columns: int
    lines: int


class _FdStream:
    def __init__(self, fd: int = 3) -> None:
        self._fd = fd

    def fileno(self) -> int:
        return self._fd


class _NoFilenoStream:
    def fileno(self) -> int:
        raise AttributeError("no fileno")


class TerminalSizeTests(unittest.TestCase):
    def test_reports_the_real_size(self) -> None:
        calls: List[int] = []

        def size_of(fd: int) -> _Size:
            calls.append(fd)
            return _Size(132, 43)

        self.assertEqual((132, 43), terminal_size(_FdStream(9), size_of))
        self.assertEqual([9], calls)

    def test_falls_back_when_the_size_is_unknown(self) -> None:
        def failing(fd: int) -> _Size:
            raise OSError("not a terminal")

        self.assertEqual((80, 24), terminal_size(_FdStream(), failing))

    def test_falls_back_when_the_stream_has_no_fileno(self) -> None:
        self.assertEqual((80, 24), terminal_size(_NoFilenoStream()))


class WindowsRawModeTests(unittest.TestCase):
    def _ops(
        self, log: List[Tuple[str, Any]], previous: int
    ) -> WindowsConsoleOps:
        def get_mode(fd: int) -> int:
            log.append(("get", fd))
            return previous

        def set_mode(fd: int, mode: int) -> None:
            log.append(("set", fd, mode))

        return WindowsConsoleOps(get_mode, set_mode)

    # 0x0001 processed + 0x0002 line input + 0x0004 echo, all set.
    _INPUT_MODE = 0x0007
    # 0x0001 processed + 0x0002 wrap; the ANSI bit is still clear.
    _OUTPUT_MODE = 0x0003

    def _input_ops(self, log: List[Tuple[str, Any]]) -> WindowsConsoleOps:
        return self._ops(log, self._INPUT_MODE)

    def _output_ops(self, log: List[Tuple[str, Any]]) -> WindowsConsoleOps:
        return self._ops(log, self._OUTPUT_MODE)

    def test_disables_line_input_and_echo_on_the_input_handle(self) -> None:
        log: List[Tuple[str, Any]] = []
        with windows_raw_mode(7, self._input_ops(log)):
            log.append(("body", None))

        self.assertEqual(("set", 7, 0x0001), log[1])

    def test_enables_ansi_on_the_output_handle(self) -> None:
        log: List[Tuple[str, Any]] = []
        with windows_raw_mode(
            7,
            self._input_ops(log),
            output_fd=1,
            output_ops=self._output_ops(log),
        ):
            log.append(("body", None))

        writes = [entry for entry in log if entry[0] == "set" and entry[1] == 1]
        self.assertEqual(("set", 1, 0x0007), writes[0])

    def test_restores_both_modes(self) -> None:
        log: List[Tuple[str, Any]] = []
        with windows_raw_mode(
            7,
            self._input_ops(log),
            output_fd=1,
            output_ops=self._output_ops(log),
        ):
            pass

        self.assertEqual(("set", 7, self._INPUT_MODE), log[-2])
        self.assertEqual(("set", 1, self._OUTPUT_MODE), log[-1])

    def test_restores_when_body_raises(self) -> None:
        log: List[Tuple[str, Any]] = []
        with self.assertRaises(KeyboardInterrupt):
            with windows_raw_mode(
                7,
                self._input_ops(log),
                output_fd=1,
                output_ops=self._output_ops(log),
            ):
                raise KeyboardInterrupt

        self.assertEqual(("set", 7, self._INPUT_MODE), log[-2])
        self.assertEqual(("set", 1, self._OUTPUT_MODE), log[-1])

    def test_leaves_the_output_mode_alone_without_an_output_fd(self) -> None:
        log: List[Tuple[str, Any]] = []
        with windows_raw_mode(7, self._input_ops(log)):
            pass

        self.assertEqual(
            [
                ("get", 7),
                ("set", 7, 0x0001),
                ("set", 7, self._INPUT_MODE),
            ],
            log,
        )


class RawModeTests(unittest.TestCase):
    def _ops(self, log: List[Tuple[str, Any]]) -> TermiosOps:
        def get_attrs(fd: int) -> str:
            log.append(("get", fd))
            return "saved-attrs"

        def set_cbreak(fd: int) -> None:
            log.append(("cbreak", fd))

        def restore_attrs(fd: int, attrs: Any) -> None:
            log.append(("restore", (fd, attrs)))

        return TermiosOps(get_attrs, set_cbreak, restore_attrs)

    def test_enters_cbreak_and_restores_on_exit(self) -> None:
        log: List[Tuple[str, Any]] = []
        with raw_mode(7, ops=self._ops(log)):
            log.append(("body", None))

        self.assertEqual(
            [
                ("get", 7),
                ("cbreak", 7),
                ("body", None),
                ("restore", (7, "saved-attrs")),
            ],
            log,
        )

    def test_restores_when_body_raises(self) -> None:
        log: List[Tuple[str, Any]] = []
        with self.assertRaises(KeyboardInterrupt):
            with raw_mode(7, ops=self._ops(log)):
                raise KeyboardInterrupt

        self.assertEqual(("restore", (7, "saved-attrs")), log[-1])

    def test_restores_when_cbreak_fails(self) -> None:
        log: List[Tuple[str, Any]] = []
        ops = self._ops(log)

        def failing_cbreak(fd: int) -> None:
            log.append(("cbreak", fd))
            raise OSError("not a tty")

        ops = TermiosOps(ops.get_attrs, failing_cbreak, ops.restore_attrs)

        with self.assertRaises(OSError):
            with raw_mode(7, ops=ops):
                log.append(("body", None))

        self.assertNotIn(("body", None), log)
        self.assertEqual(("restore", (7, "saved-attrs")), log[-1])


if __name__ == "__main__":
    unittest.main()

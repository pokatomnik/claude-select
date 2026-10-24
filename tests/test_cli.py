import io
import unittest
from typing import List, Optional

from claude_select import __version__
from claude_select.cli import HELP, parse_args, run_cli
from claude_select.errors import AuthError, ClaudeNotFoundError, TerminalError
from claude_select.models import Model

ENV = {
    "ANTHROPIC_BASE_URL": "https://api.example.com",
    "ANTHROPIC_API_KEY": "sk-test",
}


class ParseArgsTests(unittest.TestCase):
    def test_defaults(self) -> None:
        parsed = parse_args([])
        self.assertEqual([], parsed.args)
        self.assertFalse(parsed.show_help)
        self.assertFalse(parsed.show_version)

    def test_help(self) -> None:
        self.assertTrue(parse_args(["--help"]).show_help)
        self.assertTrue(parse_args(["-h"]).show_help)

    def test_version(self) -> None:
        self.assertTrue(parse_args(["--version"]).show_version)

    def test_forwards_unknown_args(self) -> None:
        parsed = parse_args(["-p", "hello"])
        self.assertEqual(["-p", "hello"], parsed.args)

    def test_strips_leading_separator(self) -> None:
        parsed = parse_args(["--", "--model", "x"])
        self.assertEqual(["--model", "x"], parsed.args)


class RunCliTests(unittest.TestCase):
    def _run(
        self,
        argv: Optional[List[str]] = None,
        environ=None,
        fetcher=None,
        selector=None,
        runner=None,
        stdin=None,
    ):
        out = io.StringIO()
        err = io.StringIO()
        code = run_cli(
            argv or [],
            environ=ENV if environ is None else environ,
            fetcher=fetcher,
            selector=selector,
            runner=runner,
            stdin=stdin,
            stdout=out,
            stderr=err,
        )
        return code, out.getvalue(), err.getvalue()

    def test_help(self) -> None:
        code, out, err = self._run(["--help"], environ={})
        self.assertEqual(0, code)
        self.assertIn("usage: claude-select", out)
        self.assertIn("ANTHROPIC_BASE_URL", out)
        self.assertEqual("", err)

    def test_help_matches_constant(self) -> None:
        _code, out, _err = self._run(["--help"], environ={})
        self.assertEqual(HELP, out)

    def test_version(self) -> None:
        code, out, err = self._run(["--version"], environ={})
        self.assertEqual(0, code)
        self.assertEqual("claude-select " + __version__ + "\n", out)
        self.assertEqual("", err)

    def test_missing_base_url(self) -> None:
        code, out, err = self._run(
            environ={},
            fetcher=lambda settings: self.fail("fetch must not run"),
        )
        self.assertEqual(1, code)
        self.assertEqual("", out)
        self.assertIn("ANTHROPIC_BASE_URL", err)

    def test_missing_credentials(self) -> None:
        code, _out, err = self._run(
            environ={"ANTHROPIC_BASE_URL": "https://api.example.com"},
            fetcher=lambda settings: self.fail("fetch must not run"),
        )
        self.assertEqual(1, code)
        self.assertIn("ANTHROPIC_API_KEY", err)
        self.assertIn("ANTHROPIC_AUTH_TOKEN", err)

    def test_settings_passed_to_fetcher(self) -> None:
        seen = {}

        def fetcher(settings):
            seen["settings"] = settings
            return [Model("a")]

        code, _out, _err = self._run(
            fetcher=fetcher,
            selector=lambda items, **kwargs: 0,
            runner=lambda model_id, args: 0,
        )

        self.assertEqual(0, code)
        self.assertEqual(
            "https://api.example.com/v1/models",
            seen["settings"].models_url,
        )
        self.assertEqual("sk-test", seen["settings"].headers()["x-api-key"])

    def test_auth_error_is_reported(self) -> None:
        def fetcher(settings):
            raise AuthError("Authentication failed (HTTP 401)")

        code, out, err = self._run(fetcher=fetcher)
        self.assertEqual(1, code)
        self.assertEqual("", out)
        self.assertIn("Authentication failed", err)
        self.assertTrue(err.startswith("claude-select: "))

    def test_empty_model_list(self) -> None:
        code, out, err = self._run(
            fetcher=lambda settings: [],
            selector=lambda items, **kwargs: self.fail("picker must not run"),
        )
        self.assertEqual(1, code)
        self.assertEqual("No models found\n", out)
        self.assertEqual("", err)

    def test_selects_model_and_runs_claude(self) -> None:
        out = io.StringIO()
        err = io.StringIO()
        stdin = io.StringIO()
        started = []
        models = [Model("model-a"), Model("model-b", "Model B")]

        def selector(items, *, input_stream, output_stream):
            self.assertEqual(["model-a", "model-b (Model B)"], items)
            self.assertIs(stdin, input_stream)
            self.assertIs(out, output_stream)
            return 1

        def runner(model_id, extra_args):
            started.append((model_id, list(extra_args)))
            return 7

        code = run_cli(
            ["-p", "hello"],
            environ=ENV,
            fetcher=lambda settings: models,
            selector=selector,
            runner=runner,
            stdin=stdin,
            stdout=out,
            stderr=err,
        )

        self.assertEqual(7, code)
        self.assertEqual([("model-b", ["-p", "hello"])], started)
        self.assertIn("Select model\n", out.getvalue())
        self.assertEqual("", err.getvalue())

    def test_cancel_does_not_run_claude(self) -> None:
        code, out, err = self._run(
            fetcher=lambda settings: [Model("a")],
            selector=lambda items, **kwargs: None,
            runner=lambda model_id, args: self.fail("claude must not run"),
        )
        self.assertEqual(130, code)
        self.assertIn("Select model", out)
        self.assertEqual("", err)

    def test_terminal_error_is_reported(self) -> None:
        def selector(items, **kwargs):
            raise TerminalError("no terminal here")

        code, _out, err = self._run(
            fetcher=lambda settings: [Model("a")],
            selector=selector,
        )
        self.assertEqual(1, code)
        self.assertIn("no terminal here", err)

    def test_real_picker_requires_terminal(self) -> None:
        code, out, err = self._run(
            fetcher=lambda settings: [Model("a")],
            stdin=io.StringIO(),
        )
        self.assertEqual(1, code)
        self.assertIn("Select model", out)
        self.assertIn("needs a terminal", err)

    def test_runner_error_is_reported(self) -> None:
        def runner(model_id, args):
            raise ClaudeNotFoundError("claude is missing")

        code, _out, err = self._run(
            fetcher=lambda settings: [Model("a")],
            selector=lambda items, **kwargs: 0,
            runner=runner,
        )
        self.assertEqual(1, code)
        self.assertIn("claude is missing", err)


if __name__ == "__main__":
    unittest.main()

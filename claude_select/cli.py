"""Command-line entry point for claude-select.

The flow is deliberately split into injectable pieces (``fetcher``,
``selector``, ``runner``) so the orchestration can be unit-tested without any
environment, filesystem, network or terminal access.
"""

from __future__ import annotations

import os
import sys
from typing import Callable, List, Mapping, NamedTuple, Optional, Sequence, TextIO

from . import __version__
from .config import Settings, settings_from_env
from .errors import ClaudeSelectError, TerminalError
from .models import Model, fetch_models
from .picker import pick
from .runner import run_claude

Fetcher = Callable[[Settings], List[Model]]
Selector = Callable[..., Optional[int]]
Runner = Callable[..., int]

HELP = """usage: claude-select [--] [claude args...]

Pick a model from the [CC] endpoint and start the [CC] CLI with that model
(runs: claude --model <selected id>).

Any arguments are forwarded to the claude command, for example:
  claude-select -p "Summarize this repository"

Environment:
  ANTHROPIC_BASE_URL         Required. API base URL used by [CC].
  ANTHROPIC_API_KEY          API key, sent as x-api-key.
  ANTHROPIC_AUTH_TOKEN       Bearer token, sent as Authorization.
  CLAUDE_SELECT_MODELS_URL   Optional. Overrides the models endpoint
                             (default: <base URL>/v1/models).

Set exactly one of ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN. Setting both is
an error; setting neither is an error.
"""


class ParsedArgs(NamedTuple):
    """Result of a minimal, forwarding-friendly argument parse."""

    args: List[str]
    show_help: bool = False
    show_version: bool = False


def parse_args(argv: Sequence[str]) -> ParsedArgs:
    """Parse only claude-select's own flags; forward everything else."""
    args = list(argv)
    if args and args[0] in ("-h", "--help"):
        return ParsedArgs([], show_help=True)
    if args and args[0] == "--version":
        return ParsedArgs([], show_version=True)
    if args and args[0] == "--":
        args = args[1:]
    return ParsedArgs(args)


def run_cli(
    argv: Optional[Sequence[str]] = None,
    *,
    environ: Optional[Mapping[str, str]] = None,
    fetcher: Optional[Fetcher] = None,
    selector: Optional[Selector] = None,
    runner: Optional[Runner] = None,
    stdin: Optional[TextIO] = None,
    stdout: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
) -> int:
    """Run the whole workflow and return a process exit code."""
    args = list(sys.argv[1:] if argv is None else argv)
    env = os.environ if environ is None else environ
    get_models = fetch_models if fetcher is None else fetcher
    choose = pick if selector is None else selector
    start = run_claude if runner is None else runner
    input_stream = sys.stdin if stdin is None else stdin
    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr

    parsed = parse_args(args)
    if parsed.show_help:
        print(HELP, file=out, end="")
        return 0
    if parsed.show_version:
        print("claude-select " + __version__, file=out)
        return 0

    try:
        settings = settings_from_env(env)
        models = get_models(settings)
    except ClaudeSelectError as exc:
        print("claude-select: " + str(exc), file=err)
        return 1

    if not models:
        print("No models found", file=out)
        return 1

    print("Select model", file=out)
    try:
        index = choose(
            [model.label for model in models],
            input_stream=input_stream,
            output_stream=out,
        )
    except TerminalError as exc:
        print("claude-select: " + str(exc), file=err)
        return 1

    if index is None:
        return 130

    out.flush()
    err.flush()
    try:
        return start(models[index].id, parsed.args)
    except ClaudeSelectError as exc:
        print("claude-select: " + str(exc), file=err)
        return 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Console-script entry point."""
    try:
        return run_cli(argv)
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

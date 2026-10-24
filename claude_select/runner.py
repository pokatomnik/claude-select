"""Launch the [CC] CLI with the selected model."""

from __future__ import annotations

import os
import shutil
from typing import Callable, List, Mapping, Optional, Sequence

from .errors import ClaudeNotFoundError
from .profiles import default_environment, model_argument

CLAUDE_BINARY = "claude"

Which = Callable[[str], Optional[str]]
Exec = Callable[[str, Sequence[str], Mapping[str, str]], None]


def build_command(model_id: str, extra_args: Sequence[str] = ()) -> List[str]:
    """Build the [CC] command line for ``model_id``."""
    return [CLAUDE_BINARY, "--model", model_argument(model_id), *extra_args]


def run_claude(
    model_id: str,
    extra_args: Sequence[str] = (),
    *,
    which: Which = shutil.which,
    execve: Exec = os.execve,
    environ: Optional[Mapping[str, str]] = None,
) -> int:
    """Replace the current process with ``claude --model <id>``.

    Known models get their profile variables unless the user already set them.
    ``execve`` never returns in production, so the trailing ``return 0`` only
    matters for tests that inject a fake executable.

    Raises:
        ClaudeNotFoundError: when the ``claude`` binary is missing or cannot
            be started.
    """
    path = which(CLAUDE_BINARY)
    if not path:
        raise ClaudeNotFoundError(
            "The '"
            + CLAUDE_BINARY
            + "' executable was not found on PATH. Install [CC], then try again."
        )

    env = dict(os.environ if environ is None else environ)
    for name, value in default_environment(model_id).items():
        if not env.get(name):
            env[name] = value

    command = build_command(model_id, extra_args)
    try:
        execve(path, command, env)
    except OSError as exc:
        raise ClaudeNotFoundError("Could not start " + path + ": " + str(exc)) from None
    return 0

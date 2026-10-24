"""User-facing errors raised by claude-select.

Every exception in this module is safe to print without a traceback: the
command line entry point catches :class:`ClaudeSelectError` and shows the
message to the user.
"""

from __future__ import annotations


class ClaudeSelectError(Exception):
    """Base class for errors that should be shown without a traceback."""


class ConfigError(ClaudeSelectError):
    """The environment is missing or contains invalid configuration."""


class AuthError(ClaudeSelectError):
    """The endpoint rejected the configured credentials."""


class ApiError(ClaudeSelectError):
    """The models endpoint returned an unexpected response."""


class NetworkError(ClaudeSelectError):
    """The models endpoint could not be reached."""


class TerminalError(ClaudeSelectError):
    """Interactive selection is not possible in the current terminal."""


class ClaudeNotFoundError(ClaudeSelectError):
    """The [CC] executable is unavailable."""

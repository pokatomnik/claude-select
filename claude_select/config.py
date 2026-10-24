"""Read and validate configuration from the environment.

The module never touches ``os.environ`` itself: callers pass a mapping, which
keeps :func:`settings_from_env` trivially unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional

from .errors import ConfigError

BASE_URL_ENV = "ANTHROPIC_BASE_URL"
API_KEY_ENV = "ANTHROPIC_API_KEY"
AUTH_TOKEN_ENV = "ANTHROPIC_AUTH_TOKEN"
MODELS_URL_ENV = "CLAUDE_SELECT_MODELS_URL"

ANTHROPIC_VERSION = "2023-06-01"


@dataclass(frozen=True)
class Settings:
    """Resolved settings used to query the models endpoint."""

    base_url: str
    models_url: str
    api_key: Optional[str] = None
    auth_token: Optional[str] = None

    def headers(self) -> Dict[str, str]:
        """Build request headers the same way the [CC] CLI does."""
        headers = {
            "accept": "application/json",
            "anthropic-version": ANTHROPIC_VERSION,
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key
        if self.auth_token:
            headers["authorization"] = "Bearer " + self.auth_token
        return headers


def models_url_from_base(base_url: str) -> str:
    """Derive the models endpoint from the API base URL.

    ``https://api.anthropic.com`` becomes
    ``https://api.anthropic.com/v1/models``, while a base URL that already
    ends in ``/v1`` only gets ``/models`` appended.
    """
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return base + "/models"
    return base + "/v1/models"


def settings_from_env(environ: Mapping[str, str]) -> Settings:
    """Validate ``environ`` and return :class:`Settings`.

    Raises:
        ConfigError: when the base URL is missing/invalid or when no
            credentials are provided.
    """
    base_url = _require_url(BASE_URL_ENV, _clean(environ.get(BASE_URL_ENV)))
    api_key = _clean(environ.get(API_KEY_ENV)) or None
    auth_token = _clean(environ.get(AUTH_TOKEN_ENV)) or None
    if not api_key and not auth_token:
        raise ConfigError(
            API_KEY_ENV
            + " and "
            + AUTH_TOKEN_ENV
            + " are both unset. Set the same credentials you use for [CC] "
            "and try again."
        )

    models_url = _clean(environ.get(MODELS_URL_ENV))
    if models_url:
        models_url = _require_url(MODELS_URL_ENV, models_url)
    else:
        models_url = models_url_from_base(base_url)

    return Settings(
        base_url=base_url,
        models_url=models_url,
        api_key=api_key,
        auth_token=auth_token,
    )


def _clean(value: Optional[str]) -> str:
    return value.strip() if value else ""


def _require_url(name: str, value: str) -> str:
    if not value:
        raise ConfigError(
            name + " is not set. [CC] uses it to locate the API endpoint; export "
            "it (for example ANTHROPIC_BASE_URL=https://api.anthropic.com) "
            "and try again."
        )
    if not value.startswith(("http://", "https://")):
        raise ConfigError(
            name + " must start with http:// or https:// (got " + repr(value) + ")."
        )
    return value

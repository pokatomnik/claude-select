"""Launch settings for [CC] models (pure data and functions, no I/O).

Models Anthropic publishes are listed with their context window and output
limit. Any other model is launched with a 1M-token context and no output
limit, so [CC] applies its own defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping

ONE_MILLION_TOKENS = 1_000_000
DEFAULT_CONTEXT_TOKENS = ONE_MILLION_TOKENS
EXTENDED_CONTEXT_SUFFIX = "[1m]"
MAX_OUTPUT_TOKENS_ENV = "CLAUDE_CODE_MAX_OUTPUT_TOKENS"


@dataclass(frozen=True)
class ModelProfile:
    """Context window and output cap of a known Anthropic model."""

    context_tokens: int
    max_output_tokens: int


_MILLION_CONTEXT = ModelProfile(ONE_MILLION_TOKENS, 128_000)
_HAIKU_4_5 = ModelProfile(200_000, 64_000)

KNOWN_MODELS: Mapping[str, ModelProfile] = {
    "claude-fable-5-1": _MILLION_CONTEXT,
    "claude-mythos-5-1": _MILLION_CONTEXT,
    "claude-fable-5": _MILLION_CONTEXT,
    "claude-mythos-5": _MILLION_CONTEXT,
    "claude-opus-5-5": _MILLION_CONTEXT,
    "claude-opus-5": _MILLION_CONTEXT,
    "claude-opus-4-8": _MILLION_CONTEXT,
    "claude-opus-4-7": _MILLION_CONTEXT,
    "claude-opus-4-6": _MILLION_CONTEXT,
    "claude-sonnet-5-5": _MILLION_CONTEXT,
    "claude-sonnet-5": _MILLION_CONTEXT,
    "claude-sonnet-4-6": _MILLION_CONTEXT,
    "claude-haiku-5-5": _MILLION_CONTEXT,
    "claude-haiku-4-5": _HAIKU_4_5,
    "claude-haiku-4-5-20251001": _HAIKU_4_5,
}


def model_argument(model_id: str) -> str:
    """Return the value passed to ``claude --model``."""
    profile = KNOWN_MODELS.get(model_id)
    context = profile.context_tokens if profile else DEFAULT_CONTEXT_TOKENS
    if context >= ONE_MILLION_TOKENS:
        return model_id + EXTENDED_CONTEXT_SUFFIX
    return model_id


def default_environment(model_id: str) -> Dict[str, str]:
    """Return the environment variables a known model needs; unknown models get none."""
    profile = KNOWN_MODELS.get(model_id)
    if profile is None:
        return {}
    return {MAX_OUTPUT_TOKENS_ENV: str(profile.max_output_tokens)}

"""Fetch and parse the model list exposed by the endpoint."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .config import Settings
from .errors import ApiError, AuthError
from .http import HttpResponse, Transport, urllib_transport

MAX_PAGES = 1000
_PAGE_SIZE = 1000
_MIN_PAGE_SIZE = 1
_SNIPPET_LIMIT = 300

_AUTH_STATUSES = (401, 403)
_LIMIT_REJECTED_STATUSES = (400, 422)


@dataclass(frozen=True)
class Model:
    """A single model advertised by the endpoint."""

    id: str
    display_name: Optional[str] = None

    @property
    def label(self) -> str:
        """Human readable label used by the picker."""
        if self.display_name and self.display_name != self.id:
            return self.id + " (" + self.display_name + ")"
        return self.id


def fetch_models(
    settings: Settings,
    transport: Optional[Transport] = None,
) -> List[Model]:
    """Return every model advertised by ``settings.models_url``.

    The list is deduplicated and keeps the order returned by the endpoint.
    Pagination is followed while the payload contains ``has_more`` and
    ``last_id`` (the Anthropic API convention); endpoints that return a
    single page need no special handling.

    The first request is sent without a ``limit`` so that any gateway is
    accepted. Every following request asks for :data:`_PAGE_SIZE` models; if
    an endpoint rejects that, the largest limit it does accept is found by
    binary search and reused for the remaining pages.
    """
    caller = transport or urllib_transport
    headers = settings.headers()

    models: List[Model] = []
    seen: Set[str] = set()
    after_id: Optional[str] = None
    limit: Optional[int] = _PAGE_SIZE

    for _ in range(MAX_PAGES):
        url, response, limit = _request_page(
            caller, headers, settings.models_url, after_id, limit
        )
        payload = _decode(url, response)
        _extend(models, seen, parse_models(payload))

        next_id = _next_after_id(payload)
        if next_id is None or next_id == after_id:
            return models
        after_id = next_id

    raise ApiError(
        "Models endpoint has more than "
        + str(MAX_PAGES)
        + " pages; the list would be incomplete."
    )


def _page_url(base_url: str, after_id: Optional[str], limit: Optional[int]) -> str:
    if after_id is None:
        return base_url
    params = {"after_id": after_id}
    if limit is not None:
        params["limit"] = str(limit)
    return _with_query(base_url, params)


def _request_page(
    caller: Transport,
    headers: Dict[str, str],
    base_url: str,
    after_id: Optional[str],
    limit: Optional[int],
) -> Tuple[str, HttpResponse, Optional[int]]:
    """Request one page, shrinking ``limit`` when the endpoint rejects it."""
    url = _page_url(base_url, after_id, limit)
    response = caller(url, headers)
    if after_id is None or limit is None or not _limit_rejected(response):
        return url, response, limit

    found = _largest_accepted_limit(caller, headers, base_url, after_id, limit)
    if found is not None:
        return found

    url = _page_url(base_url, after_id, None)
    return url, caller(url, headers), None


def _largest_accepted_limit(
    caller: Transport,
    headers: Dict[str, str],
    base_url: str,
    after_id: Optional[str],
    upper: int,
) -> Optional[Tuple[str, HttpResponse, Optional[int]]]:
    """Binary-search the largest ``limit`` below ``upper`` the endpoint takes."""
    low, high = _MIN_PAGE_SIZE, upper - 1
    best = None
    while low <= high:
        middle = (low + high) // 2
        url = _page_url(base_url, after_id, middle)
        response = caller(url, headers)
        if _limit_rejected(response):
            high = middle - 1
        else:
            best = (url, response, middle)
            low = middle + 1
    return best


def _extend(
    models: List[Model], seen: Set[str], found: Iterable[Model]
) -> None:
    for model in found:
        if model.id not in seen:
            seen.add(model.id)
            models.append(model)


def parse_models(payload: Any) -> List[Model]:
    """Extract models from a decoded JSON payload.

    Supports the shapes used by Anthropic-compatible endpoints
    (``{"data": [...]}``), [OI]-compatible endpoints (also ``data``), Ollama
    (``{"models": [...]}``) and a bare JSON array. Unknown shapes yield an
    empty list instead of an exception.
    """
    models: List[Model] = []
    seen: Set[str] = set()

    for entry in _entries(payload):
        model = _entry_to_model(entry)
        if model is not None and model.id not in seen:
            seen.add(model.id)
            models.append(model)

    return models


def _entries(payload: Any) -> List[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "models"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def _entry_to_model(entry: Any) -> Optional[Model]:
    if isinstance(entry, str):
        identifier = entry.strip()
        return Model(identifier) if identifier else None
    if not isinstance(entry, dict):
        return None

    identifier = _first_string(entry, ("id", "model", "name"))
    if not identifier:
        return None
    display_name = _first_string(entry, ("display_name", "displayName", "name"))
    return Model(identifier, display_name)


def _first_string(entry: Mapping[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _decode(url: str, response: HttpResponse) -> Any:
    if response.status in _AUTH_STATUSES:
        raise AuthError(
            "Authentication failed (HTTP "
            + str(response.status)
            + ") for "
            + url
            + ". Check ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN."
        )
    if response.status >= 400:
        raise ApiError(
            "Models endpoint returned HTTP "
            + str(response.status)
            + ": "
            + _error_detail(response.body)
        )
    if not response.body.strip():
        raise ApiError("Models endpoint returned an empty response: " + url)

    try:
        return json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ApiError(
            "Models endpoint returned invalid JSON: " + _snippet(response.body)
        ) from None


def _next_after_id(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict) or not payload.get("has_more"):
        return None
    last_id = payload.get("last_id")
    if not isinstance(last_id, str) or not last_id.strip():
        return None
    return last_id.strip()


def _limit_rejected(response: HttpResponse) -> bool:
    """Return ``True`` when the endpoint refused the ``limit`` parameter."""
    return response.status in _LIMIT_REJECTED_STATUSES


def _with_query(url: str, params: Dict[str, str]) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(params)
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def _error_detail(body: bytes) -> str:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _snippet(body)

    if isinstance(payload, dict):
        error = payload.get("error")
        message: Any = None
        if isinstance(error, dict):
            message = error.get("message") or error.get("type")
        elif isinstance(error, str):
            message = error
        if not message:
            message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return _snippet(body)


def _snippet(body: bytes) -> str:
    text = " ".join(body.decode("utf-8", "replace").split())
    if not text:
        return "(empty body)"
    return text[:_SNIPPET_LIMIT]

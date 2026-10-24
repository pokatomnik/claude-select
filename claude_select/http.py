"""Minimal HTTP transport built on :mod:`urllib` (no third-party packages)."""

from __future__ import annotations

import urllib.error
import urllib.request
from typing import Callable, Mapping, NamedTuple

from .errors import NetworkError


class HttpResponse(NamedTuple):
    """Status code and raw body returned by a transport call."""

    status: int
    body: bytes


Transport = Callable[[str, Mapping[str, str]], HttpResponse]


def urllib_transport(
    url: str,
    headers: Mapping[str, str],
    timeout: float = 30.0,
) -> HttpResponse:
    """Perform a GET request and return status + body.

    HTTP error responses are returned as :class:`HttpResponse` values so the
    caller can produce a helpful message; connection failures raise
    :class:`NetworkError`.
    """
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return HttpResponse(response.status, response.read())
    except urllib.error.HTTPError as exc:
        body = exc.read()
        exc.close()
        return HttpResponse(exc.code, body)
    except urllib.error.URLError as exc:
        raise NetworkError("Could not reach " + url + ": " + str(exc.reason)) from None
    except OSError as exc:
        raise NetworkError("Could not reach " + url + ": " + str(exc)) from None

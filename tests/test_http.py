import http.client
import io
import unittest
import urllib.error
from typing import Any

from claude_select.errors import NetworkError
from claude_select.http import HttpResponse, urllib_transport


class FakeResponse(io.BytesIO):
    def __init__(self, status: int, body: bytes) -> None:
        super().__init__(body)
        self.status = status

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()


def opener_returning(status: int, body: bytes):
    def opener(request: Any, timeout: float) -> FakeResponse:
        return FakeResponse(status, body)

    return opener


def opener_raising(error: BaseException):
    def opener(request: Any, timeout: float) -> FakeResponse:
        raise error

    return opener


class UrllibTransportTests(unittest.TestCase):
    def test_returns_status_and_body(self) -> None:
        result = urllib_transport(
            "https://api.example.com/v1/models",
            {"x-api-key": "sk-test"},
            opener=opener_returning(200, b"{}"),
        )
        self.assertEqual(HttpResponse(200, b"{}"), result)

    def test_http_error_is_returned_as_response(self) -> None:
        error = urllib.error.HTTPError(
            "https://api.example.com/v1/models",
            401,
            "Unauthorized",
            {},
            io.BytesIO(b'{"error": "nope"}'),
        )
        result = urllib_transport(
            "https://api.example.com/v1/models",
            {},
            opener=opener_raising(error),
        )
        self.assertEqual(401, result.status)
        self.assertEqual(b'{"error": "nope"}', result.body)

    def test_url_error_becomes_network_error(self) -> None:
        with self.assertRaises(NetworkError) as raised:
            urllib_transport(
                "https://api.example.com/v1/models",
                {},
                opener=opener_raising(urllib.error.URLError("refused")),
            )
        self.assertIn("refused", str(raised.exception))

    def test_malformed_url_becomes_network_error(self) -> None:
        with self.assertRaises(NetworkError) as raised:
            urllib_transport(
                "https://example.com:abc/models",
                {},
                opener=opener_raising(
                    http.client.InvalidURL("nonnumeric port: 'abc'")
                ),
            )
        self.assertIn("nonnumeric port", str(raised.exception))
        self.assertIn("https://example.com:abc/models", str(raised.exception))

    def test_value_error_becomes_network_error(self) -> None:
        with self.assertRaises(NetworkError):
            urllib_transport(
                "https://api.example.com/v1/models",
                {},
                opener=opener_raising(ValueError("bad header")),
            )


if __name__ == "__main__":
    unittest.main()

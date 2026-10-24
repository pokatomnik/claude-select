import json
import unittest
from typing import Any, List, Mapping, Tuple

from claude_select.config import Settings
from claude_select.errors import ApiError, AuthError, NetworkError
from claude_select.http import HttpResponse
from claude_select.models import Model, fetch_models, parse_models


def make_settings(**overrides: Any) -> Settings:
    values = {
        "base_url": "https://api.example.com",
        "models_url": "https://api.example.com/v1/models",
        "api_key": "sk-test",
    }
    values.update(overrides)
    return Settings(**values)


class FakeTransport:
    def __init__(self, responses: List[HttpResponse]) -> None:
        self.responses = list(responses)
        self.calls: List[Tuple[str, Mapping[str, str]]] = []

    def __call__(self, url: str, headers: Mapping[str, str]) -> HttpResponse:
        self.calls.append((url, dict(headers)))
        if not self.responses:
            raise AssertionError("unexpected request to " + url)
        return self.responses.pop(0)


def response(status: int, payload: Any) -> HttpResponse:
    if isinstance(payload, bytes):
        body = payload
    else:
        body = json.dumps(payload).encode("utf-8")
    return HttpResponse(status, body)


class ParseModelsTests(unittest.TestCase):
    def test_parses_anthropic_payload(self) -> None:
        payload = {
            "data": [
                {
                    "type": "model",
                    "id": "the-model-4",
                    "display_name": "The Model 4",
                }
            ],
            "has_more": False,
        }
        self.assertEqual(
            [Model("the-model-4", "The Model 4")],
            parse_models(payload),
        )

    def test_parses_openai_payload(self) -> None:
        payload = {
            "object": "list",
            "data": [{"id": "gpt-4o", "object": "model"}],
        }
        self.assertEqual([Model("gpt-4o")], parse_models(payload))

    def test_parses_ollama_payload(self) -> None:
        payload = {"models": [{"name": "llama3.2:latest"}]}
        models = parse_models(payload)
        self.assertEqual(["llama3.2:latest"], [model.id for model in models])
        self.assertEqual("llama3.2:latest", models[0].label)

    def test_parses_bare_list(self) -> None:
        self.assertEqual([Model("a"), Model("b")], parse_models(["a", " b "]))

    def test_deduplicates_by_id(self) -> None:
        payload = {"data": [{"id": "a"}, {"id": "a", "display_name": "A"}]}
        self.assertEqual([Model("a")], parse_models(payload))

    def test_skips_invalid_entries(self) -> None:
        payload = {
            "data": [None, 42, {}, {"id": "   "}, {"id": "good"}],
        }
        self.assertEqual([Model("good")], parse_models(payload))

    def test_ignores_unknown_shapes(self) -> None:
        for payload in (None, 1, "nope", {}, {"data": "nope"}):
            self.assertEqual([], parse_models(payload))

    def test_reads_id_and_name(self) -> None:
        payload = {"data": [{"name": "My Model", "id": "m"}]}
        self.assertEqual([Model("m", "My Model")], parse_models(payload))

    def test_label_formats(self) -> None:
        self.assertEqual("abc", Model("abc").label)
        self.assertEqual("abc (ABC)", Model("abc", "ABC").label)
        self.assertEqual("abc", Model("abc", "abc").label)


class FetchModelsTests(unittest.TestCase):
    def test_returns_models_and_sends_headers(self) -> None:
        transport = FakeTransport([response(200, {"data": [{"id": "a"}]})])
        settings = make_settings()

        models = fetch_models(settings, transport)

        self.assertEqual([Model("a")], models)
        self.assertEqual(1, len(transport.calls))
        url, headers = transport.calls[0]
        self.assertEqual("https://api.example.com/v1/models", url)
        self.assertEqual("sk-test", headers["x-api-key"])

    def test_empty_list_is_not_an_error(self) -> None:
        transport = FakeTransport([response(200, {"data": []})])
        self.assertEqual([], fetch_models(make_settings(), transport))

    def test_follows_pagination(self) -> None:
        transport = FakeTransport(
            [
                response(
                    200,
                    {"data": [{"id": "a"}], "has_more": True, "last_id": "a"},
                ),
                response(200, {"data": [{"id": "b"}], "has_more": False}),
            ]
        )

        models = fetch_models(make_settings(), transport)

        self.assertEqual([Model("a"), Model("b")], models)
        self.assertEqual(2, len(transport.calls))
        second_url = transport.calls[1][0]
        self.assertIn("after_id=a", second_url)
        self.assertIn("limit=1000", second_url)
        self.assertTrue(second_url.startswith("https://api.example.com/v1/models?"))

    def test_deduplicates_across_pages(self) -> None:
        transport = FakeTransport(
            [
                response(
                    200,
                    {"data": [{"id": "a"}], "has_more": True, "last_id": "a"},
                ),
                response(200, {"data": [{"id": "a"}, {"id": "b"}]}),
            ]
        )
        self.assertEqual(
            [Model("a"), Model("b")],
            fetch_models(make_settings(), transport),
        )

    def test_stops_when_has_more_has_no_last_id(self) -> None:
        transport = FakeTransport(
            [response(200, {"data": [{"id": "a"}], "has_more": True})]
        )
        self.assertEqual([Model("a")], fetch_models(make_settings(), transport))
        self.assertEqual(1, len(transport.calls))

    def test_auth_error_for_401(self) -> None:
        transport = FakeTransport([response(401, {"error": "nope"})])
        with self.assertRaises(AuthError) as raised:
            fetch_models(make_settings(), transport)
        message = str(raised.exception)
        self.assertIn("401", message)
        self.assertIn("ANTHROPIC_API_KEY", message)

    def test_auth_error_for_403(self) -> None:
        transport = FakeTransport([response(403, b"")])
        with self.assertRaises(AuthError):
            fetch_models(make_settings(), transport)

    def test_api_error_includes_json_message(self) -> None:
        transport = FakeTransport(
            [response(500, {"error": {"message": "upstream exploded"}})]
        )
        with self.assertRaises(ApiError) as raised:
            fetch_models(make_settings(), transport)
        self.assertIn("500", str(raised.exception))
        self.assertIn("upstream exploded", str(raised.exception))

    def test_api_error_includes_plain_body(self) -> None:
        transport = FakeTransport([response(502, b"bad gateway")])
        with self.assertRaises(ApiError) as raised:
            fetch_models(make_settings(), transport)
        self.assertIn("bad gateway", str(raised.exception))

    def test_invalid_json(self) -> None:
        transport = FakeTransport([response(200, b"<html>nope</html>")])
        with self.assertRaises(ApiError) as raised:
            fetch_models(make_settings(), transport)
        self.assertIn("invalid JSON", str(raised.exception))

    def test_empty_body(self) -> None:
        transport = FakeTransport([HttpResponse(200, b"   \n")])
        with self.assertRaises(ApiError) as raised:
            fetch_models(make_settings(), transport)
        self.assertIn("empty response", str(raised.exception))

    def test_network_error_propagates(self) -> None:
        def failing_transport(url: str, headers: Mapping[str, str]) -> HttpResponse:
            raise NetworkError("Could not reach " + url)

        with self.assertRaises(NetworkError):
            fetch_models(make_settings(), failing_transport)

    def test_uses_auth_token_header_when_configured(self) -> None:
        transport = FakeTransport([response(200, {"data": []})])
        fetch_models(
            make_settings(api_key=None, auth_token="token"),
            transport,
        )
        headers = transport.calls[0][1]
        self.assertEqual("Bearer token", headers["authorization"])
        self.assertNotIn("x-api-key", headers)


if __name__ == "__main__":
    unittest.main()

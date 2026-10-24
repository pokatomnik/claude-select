import unittest

from claude_select.config import (
    API_KEY_ENV,
    AUTH_TOKEN_ENV,
    BASE_URL_ENV,
    MODELS_URL_ENV,
    Settings,
    models_url_from_base,
    settings_from_env,
)
from claude_select.errors import ConfigError


class ModelsUrlFromBaseTests(unittest.TestCase):
    def test_appends_v1_models(self) -> None:
        self.assertEqual(
            "https://api.anthropic.com/v1/models",
            models_url_from_base("https://api.anthropic.com"),
        )

    def test_trims_trailing_slash(self) -> None:
        self.assertEqual(
            "https://api.anthropic.com/v1/models",
            models_url_from_base("https://api.anthropic.com/"),
        )

    def test_keeps_existing_v1_suffix(self) -> None:
        self.assertEqual(
            "https://proxy.example.com/v1/models",
            models_url_from_base("https://proxy.example.com/v1"),
        )

    def test_handles_v1_with_trailing_slash(self) -> None:
        self.assertEqual(
            "https://proxy.example.com/v1/models",
            models_url_from_base("https://proxy.example.com/v1/"),
        )


class SettingsFromEnvTests(unittest.TestCase):
    def test_requires_base_url(self) -> None:
        with self.assertRaises(ConfigError) as raised:
            settings_from_env({API_KEY_ENV: "sk-test"})
        self.assertIn(BASE_URL_ENV, str(raised.exception))
        self.assertIn("is not set", str(raised.exception))

    def test_rejects_blank_base_url(self) -> None:
        with self.assertRaises(ConfigError):
            settings_from_env({BASE_URL_ENV: "   ", API_KEY_ENV: "sk-test"})

    def test_rejects_relative_base_url(self) -> None:
        with self.assertRaises(ConfigError) as raised:
            settings_from_env({BASE_URL_ENV: "api.example.com", API_KEY_ENV: "sk-test"})
        self.assertIn("http://", str(raised.exception))

    def test_requires_credentials(self) -> None:
        with self.assertRaises(ConfigError) as raised:
            settings_from_env({BASE_URL_ENV: "https://api.example.com"})
        message = str(raised.exception)
        self.assertIn(API_KEY_ENV, message)
        self.assertIn(AUTH_TOKEN_ENV, message)

    def test_accepts_api_key_only(self) -> None:
        settings = settings_from_env(
            {BASE_URL_ENV: "https://api.example.com", API_KEY_ENV: "sk-test"}
        )
        self.assertEqual("sk-test", settings.api_key)
        self.assertIsNone(settings.auth_token)

    def test_accepts_auth_token_only(self) -> None:
        settings = settings_from_env(
            {BASE_URL_ENV: "https://api.example.com", AUTH_TOKEN_ENV: "token"}
        )
        self.assertIsNone(settings.api_key)
        self.assertEqual("token", settings.auth_token)

    def test_rejects_both_credentials(self) -> None:
        with self.assertRaises(ConfigError) as raised:
            settings_from_env(
                {
                    BASE_URL_ENV: "https://api.example.com",
                    API_KEY_ENV: "sk-test",
                    AUTH_TOKEN_ENV: "token",
                }
            )
        message = str(raised.exception)
        self.assertIn(API_KEY_ENV, message)
        self.assertIn(AUTH_TOKEN_ENV, message)
        self.assertIn("Unset one", message)

    def test_blank_second_credential_is_not_a_conflict(self) -> None:
        settings = settings_from_env(
            {
                BASE_URL_ENV: "https://api.example.com",
                API_KEY_ENV: "sk-test",
                AUTH_TOKEN_ENV: "   ",
            }
        )
        self.assertEqual("sk-test", settings.api_key)
        self.assertIsNone(settings.auth_token)


class ModelsUrlOverrideTests(unittest.TestCase):
    def test_defaults_to_the_base_url(self) -> None:
        settings = settings_from_env(
            {BASE_URL_ENV: "https://api.example.com", API_KEY_ENV: "sk-test"}
        )
        self.assertEqual("https://api.example.com/v1/models", settings.models_url)

    def test_override(self) -> None:
        settings = settings_from_env(
            {
                BASE_URL_ENV: "https://api.example.com",
                AUTH_TOKEN_ENV: "token",
                MODELS_URL_ENV: "https://catalog.example.com/models",
            }
        )
        self.assertEqual("https://catalog.example.com/models", settings.models_url)

    def test_rejects_a_relative_override(self) -> None:
        with self.assertRaises(ConfigError) as raised:
            settings_from_env(
                {
                    BASE_URL_ENV: "https://api.example.com",
                    API_KEY_ENV: "sk-test",
                    MODELS_URL_ENV: "catalog.example.com/models",
                }
            )
        self.assertIn(MODELS_URL_ENV, str(raised.exception))


class HeadersTests(unittest.TestCase):
    def _settings(self, **kwargs: object) -> Settings:
        values = {
            "base_url": "https://api.example.com",
            "models_url": "https://api.example.com/v1/models",
        }
        values.update(kwargs)
        return Settings(**values)  # type: ignore[arg-type]

    def test_api_key_header(self) -> None:
        headers = self._settings(api_key="sk-test").headers()
        self.assertEqual("sk-test", headers["x-api-key"])
        self.assertNotIn("authorization", headers)
        self.assertEqual("2023-06-01", headers["anthropic-version"])

    def test_auth_token_header(self) -> None:
        headers = self._settings(auth_token="token").headers()
        self.assertEqual("Bearer token", headers["authorization"])
        self.assertNotIn("x-api-key", headers)

    def test_both_credentials(self) -> None:
        headers = self._settings(api_key="sk-test", auth_token="token").headers()
        self.assertEqual("sk-test", headers["x-api-key"])
        self.assertEqual("Bearer token", headers["authorization"])

    def test_headers_are_fresh_copies(self) -> None:
        settings = self._settings(api_key="sk-test")
        first = settings.headers()
        first["x-api-key"] = "changed"
        self.assertEqual("sk-test", settings.headers()["x-api-key"])


if __name__ == "__main__":
    unittest.main()

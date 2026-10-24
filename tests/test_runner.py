import unittest

from claude_select.errors import ClaudeNotFoundError
from claude_select.profiles import (
    DEFAULT_CONTEXT_TOKENS,
    KNOWN_MODELS,
    MAX_OUTPUT_TOKENS_ENV,
    ONE_MILLION_TOKENS,
    default_environment,
    model_argument,
)
from claude_select.runner import build_command, run_claude


class ModelArgumentTests(unittest.TestCase):
    def test_known_million_context_model_gets_suffix(self) -> None:
        self.assertEqual("claude-opus-5-5[1m]", model_argument("claude-opus-5-5"))

    def test_known_small_context_model_has_no_suffix(self) -> None:
        self.assertEqual(
            "claude-haiku-4-5",
            model_argument("claude-haiku-4-5"),
        )

    def test_unknown_model_gets_million_context_suffix(self) -> None:
        self.assertEqual("glm-4.6[1m]", model_argument("glm-4.6"))

    def test_existing_suffix_is_not_doubled(self) -> None:
        self.assertEqual("glm-4.6[1m]", model_argument("glm-4.6[1m]"))
        self.assertEqual("glm-4.6[1M]", model_argument("glm-4.6[1M]"))
        self.assertEqual("claude-opus-5-5[1m]", model_argument("claude-opus-5-5[1m]"))

    def test_known_model_with_suffix_keeps_profile_limit(self) -> None:
        self.assertEqual(
            {MAX_OUTPUT_TOKENS_ENV: "128000"},
            default_environment("claude-opus-5-5[1m]"),
        )

    def test_default_context_is_one_million(self) -> None:
        self.assertEqual(1_000_000, DEFAULT_CONTEXT_TOKENS)


class DefaultEnvironmentTests(unittest.TestCase):
    def test_known_model_sets_output_limit(self) -> None:
        self.assertEqual(
            {MAX_OUTPUT_TOKENS_ENV: "128000"},
            default_environment("claude-opus-5-5"),
        )

    def test_known_small_model_sets_its_own_output_limit(self) -> None:
        self.assertEqual(
            {MAX_OUTPUT_TOKENS_ENV: "64000"},
            default_environment("claude-haiku-4-5"),
        )

    def test_unknown_model_sets_nothing(self) -> None:
        self.assertEqual({}, default_environment("glm-4.6"))

    def test_known_models_are_all_anthropic_ids(self) -> None:
        for model_id in KNOWN_MODELS:
            self.assertTrue(model_id.startswith("claude-"), model_id)

    def test_every_known_profile_has_positive_limits(self) -> None:
        for model_id, profile in KNOWN_MODELS.items():
            self.assertGreater(profile.context_tokens, 0, model_id)
            self.assertGreater(profile.max_output_tokens, 0, model_id)

    def test_million_context_profiles_match_suffix_rule(self) -> None:
        for model_id, profile in KNOWN_MODELS.items():
            expected_suffix = profile.context_tokens >= ONE_MILLION_TOKENS
            self.assertEqual(
                expected_suffix,
                model_argument(model_id).endswith("[1m]"),
                model_id,
            )


class BuildCommandTests(unittest.TestCase):
    def test_sets_model_flag_with_unknown_model(self) -> None:
        self.assertEqual(
            ["claude", "--model", "m[1m]"],
            build_command("m"),
        )

    def test_forwards_extra_args(self) -> None:
        self.assertEqual(
            ["claude", "--model", "m[1m]", "-p", "hello"],
            build_command("m", ["-p", "hello"]),
        )

    def test_known_model_keeps_id_and_suffix(self) -> None:
        self.assertEqual(
            ["claude", "--model", "claude-sonnet-5-5[1m]"],
            build_command("claude-sonnet-5-5"),
        )


class RunClaudeTests(unittest.TestCase):
    def test_execs_resolved_binary(self) -> None:
        calls = []

        def fake_execve(path: str, args, env) -> None:
            calls.append((path, list(args), dict(env)))

        code = run_claude(
            "m",
            ["--verbose"],
            which=lambda name: "/opt/bin/claude",
            execve=fake_execve,
            environ={"PATH": "/usr/bin"},
        )

        self.assertEqual(0, code)
        self.assertEqual(
            [
                (
                    "/opt/bin/claude",
                    ["claude", "--model", "m[1m]", "--verbose"],
                    {"PATH": "/usr/bin"},
                )
            ],
            calls,
        )

    def test_unknown_model_leaves_environment_untouched(self) -> None:
        seen = {}

        def fake_execve(path: str, args, env) -> None:
            seen["env"] = dict(env)

        run_claude(
            "glm-4.6",
            which=lambda name: "/opt/bin/claude",
            execve=fake_execve,
            environ={"PATH": "/usr/bin"},
        )

        self.assertNotIn(MAX_OUTPUT_TOKENS_ENV, seen["env"])

    def test_known_model_sets_output_limit(self) -> None:
        seen = {}

        def fake_execve(path: str, args, env) -> None:
            seen["env"] = dict(env)

        run_claude(
            "claude-opus-5-5",
            which=lambda name: "/opt/bin/claude",
            execve=fake_execve,
            environ={"PATH": "/usr/bin"},
        )

        self.assertEqual("128000", seen["env"][MAX_OUTPUT_TOKENS_ENV])
        self.assertEqual("/usr/bin", seen["env"]["PATH"])

    def test_user_value_overrides_profile(self) -> None:
        seen = {}

        def fake_execve(path: str, args, env) -> None:
            seen["env"] = dict(env)

        run_claude(
            "claude-opus-5-5",
            which=lambda name: "/opt/bin/claude",
            execve=fake_execve,
            environ={MAX_OUTPUT_TOKENS_ENV: "4000"},
        )

        self.assertEqual("4000", seen["env"][MAX_OUTPUT_TOKENS_ENV])

    def test_empty_user_value_is_replaced_by_profile(self) -> None:
        seen = {}

        def fake_execve(path: str, args, env) -> None:
            seen["env"] = dict(env)

        run_claude(
            "claude-opus-5-5",
            which=lambda name: "/opt/bin/claude",
            execve=fake_execve,
            environ={MAX_OUTPUT_TOKENS_ENV: ""},
        )

        self.assertEqual("128000", seen["env"][MAX_OUTPUT_TOKENS_ENV])

    def test_missing_binary(self) -> None:
        with self.assertRaises(ClaudeNotFoundError) as raised:
            run_claude(
                "m",
                which=lambda name: None,
                execve=lambda path, args, env: None,
                environ={},
            )
        self.assertIn("claude", str(raised.exception))

    def test_exec_failure(self) -> None:
        def failing_execve(path: str, args, env) -> None:
            raise OSError("permission denied")

        with self.assertRaises(ClaudeNotFoundError) as raised:
            run_claude(
                "m",
                which=lambda name: "/opt/bin/claude",
                execve=failing_execve,
                environ={},
            )
        self.assertIn("permission denied", str(raised.exception))


if __name__ == "__main__":
    unittest.main()

# AGENTS.md

Guidance for AI agents and humans working on `claude-select`.

## What this project is

`claude-select` is a small, dependency-free Python wrapper around the [CC] CLI.
It reads the same environment variables [CC] uses, fetches the model catalog
from the configured endpoint, shows an arrow-key picker, and `exec`s
`claude --model <selected id>`.

## Layout

```
claude_select/
  __init__.py    version
  __main__.py    python -m claude_select
  cli.py         argument parsing, orchestration, exit codes
  config.py      env -> Settings, headers, models URL derivation
  errors.py      ClaudeSelectError hierarchy (user-facing messages)
  http.py        urllib transport (status + raw body)
  models.py      fetch, paginate, parse model catalogs
  keys.py        Key enum + pure byte/unicode decoding
  terminal.py    raw mode, key reads, ANSI Screen
  picker.py      PickerState (pure) + interactive pick()
  profiles.py    known Anthropic model profiles, [1m] suffix, output limits
  runner.py      claude command construction + exec
tests/           unittest suite (offline, no I/O)
```

## Invariants

1. **Standard library only at runtime.** Do not add third-party runtime
   dependencies without a strong, discussed reason. `urllib`, `termios`,
   `msvcrt`, `json` and friends are enough.
2. **Pure core, thin edges.** `settings_from_env` takes a mapping; the HTTP
   transport is an injectable callable; `PickerState` and key decoding do no
   I/O. Environment, network, subprocess and terminal access live only in
   `cli.py`, `http.py`, `terminal.py` and `runner.py`.
3. **Tests stay offline.** Unit tests must not read `os.environ`, files, the
   network or a real terminal. Inject fakes. Do not use `unittest.mock.patch`
   on `os.environ` — pass a dict instead.
4. **Actions must not be destructive.** Never commit unless asked.
5. **User-facing errors are short and actionable.** Raise a subclass of
   `ClaudeSelectError`; `cli.py` prints it as `claude-select: <message>`.
6. **Strings tests rely on:** `Select model`, `No models found`, the
   `claude-select: ` prefix, and the env variable names. Change them only
   together with the tests and README.
7. **Exactly one credential.** `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN`
   are alternatives: setting both is a `ConfigError`, and a blank value does
   not count as set. This is a deliberate divergence from [CC], which sends
   both headers.
8. **The whole catalog is fetched or the run fails.** Pagination follows
   `has_more` + `last_id`; the first request omits `limit`, later ones ask for
   1000 and fall back to a binary-searched limit on 400/422. Never truncate
   silently — hitting `MAX_PAGES` raises `ApiError`.
9. **Line width is capped, not measured.** The picker truncates labels at
   `MAX_LINE_WIDTH` (200) characters instead of querying the terminal width,
   because a wrapped line breaks `Screen.draw`'s cursor arithmetic.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success; in practice the process has been replaced by `claude`, so the shell sees claude's status. |
| `1` | Configuration, API, terminal error, or empty model list. |
| `130` | The user cancelled the picker. |

## Common tasks

- **Run tests:** `python -m unittest discover -s tests -t .`
- **Run manually:** `python -m claude_select` with `ANTHROPIC_BASE_URL` and a
  credential exported.
- **Add an environment variable:** add a constant and validation in
  `config.py`, a test in `tests/test_config.py`, and a README table row.
- **Support a new catalog shape:** extend `parse_models` / `_entries` in
  `models.py` and cover it in `tests/test_models.py`.
- **Change pagination:** `fetch_models` / `_request_page` in `models.py`;
  keep the no-`limit` first request and cover the change in
  `tests/test_models.py` with `catalog_transport`.
- **Change picker behavior:** pure logic in `PickerState` (`picker.py`), key
  maps in `keys.py`, terminal plumbing in `terminal.py`.
- **Change how claude is started:** `build_command` / `run_claude` in
  `runner.py`; keep `--model <id>` immediately after the binary.
- **Add or update a known Anthropic model:** add an entry to `KNOWN_MODELS` in
  `profiles.py` with its context window and output limit, and cover it in
  `tests/test_runner.py`. Unknown models need no entry: they get `[1m]`.

## Style

- Python 3.9+, type hints, `from __future__ import annotations`.
- `unittest` only; no pytest.
- Small modules with one responsibility; no service locators or global state.
- Plain DOM-less logic: return values, do not print from library modules.
  Output goes through streams passed into `pick()` or `run_cli()`.
- Comments explain intent; avoid restating code.

## Release checklist

1. Bump `__version__` in `claude_select/__init__.py` and `version` in
   `pyproject.toml` (keep them equal).
2. Run the test suite.
3. Update `README.md` and this file if behavior or layout changed.
4. Tag and build with `python -m build` (requires the `build` package, a
   development-only tool).

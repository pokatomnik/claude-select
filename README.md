# claude-select

A tiny, dependency-free wrapper around the [CC] CLI. It loads the model catalog
from your endpoint, lets you pick a model with the arrow keys, and starts
[CC] with that model:

```console
$ claude-select
Select model
> glm-4.6
  kimi-k2
```

## Why

[CC] only ships with Anthropic models, but it honours the `--model` flag for any
Anthropic-compatible gateway. `claude-select` reuses the endpoint and
credentials that [CC] already reads from the environment, so switching models
does not require editing settings or remembering model ids.

## Requirements

- Python 3.9 or newer
- [CC] CLI available as `claude` on `PATH`
- An endpoint that exposes a model catalog (by default `GET /v1/models`)

No third-party packages are required at runtime.

## Install

From a checkout of this repository:

```sh
pipx install .
```

or, inside a virtual environment:

```sh
pip install .
```

Both `pip` and `pipx` create the `claude-select` command; the module is also
runnable as `python -m claude_select`.

To install straight from GitHub with [uv](https://docs.astral.sh/uv/):

```sh
uv tool install git+https://github.com/OWNER/claude-select
```

Pin a release tag or commit by appending it to the URL:

```sh
uv tool install git+https://github.com/OWNER/claude-select@v0.1.0
```

Update to the latest version, or reinstall after a change:

```sh
uv tool upgrade claude-select
uv tool install --force git+https://github.com/OWNER/claude-select
```

Run once without installing:

```sh
uvx --from git+https://github.com/OWNER/claude-select claude-select
```

## Usage

```sh
claude-select
# or
python -m claude_select
```

Any arguments are forwarded to `claude`, so the picker can be combined with
regular flags:

```sh
claude-select -p "Explain this repository"
claude-select -- --resume
```

Use `--` when an argument could be mistaken for an option of
`claude-select` itself.

Picker controls: Up/Down (or `k`/`j`) to move, Home/End (or `g`/`G`) to jump,
Enter to confirm, Esc or `q` to cancel.

### About `claude select`

`claude` is already the [CC] binary, so the console script is named
`claude-select`. If you prefer the `claude select` spelling, add a shell
function to your profile:

```sh
claude() {
  if [ "$1" = "select" ]; then
    shift
    claude-select "$@"
  else
    command claude "$@"
  fi
}
```

## Configuration

`claude-select` deliberately uses the variables [CC] already reads:

| Variable                   | Required                | Purpose                                                                                                                      |
| -------------------------- | ----------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `ANTHROPIC_BASE_URL`       | yes                     | API base URL of your endpoint.                                                                                               |
| `ANTHROPIC_API_KEY`        | at least one credential | Sent as the `x-api-key` header.                                                                                              |
| `ANTHROPIC_AUTH_TOKEN`     | at least one credential | Sent as `Authorization: Bearer <token>`.                                                                                     |
| `CLAUDE_SELECT_MODELS_URL` | no                      | Overrides the models endpoint. Defaults to `<base>/v1/models`, or `<base>/models` when the base URL already ends with `/v1`. |

Most gateways expect `ANTHROPIC_AUTH_TOKEN`; the official Anthropic API uses
`ANTHROPIC_API_KEY`. If your provider exposes the catalog under a different
path, set `CLAUDE_SELECT_MODELS_URL`.

```sh
export ANTHROPIC_BASE_URL="https://api.anthropic.com"
export ANTHROPIC_API_KEY="sk-ant-..."
claude-select
```

The models endpoint may return any of these shapes:

- Anthropic: `{"data": [{"id": "...", "display_name": "..."}]}`
- [OI]: `{"data": [{"id": "..."}]}`
- Ollama: `{"models": [{"name": "..."}]}`
- a bare JSON array of strings or objects

Anthropic-style pagination (`has_more` + `last_id`) is followed automatically.

### Launch settings per model

`claude-select` starts `claude --model <id>` with settings that depend on the
model:

- **Known Anthropic models** have a built-in profile (context window and
  output limit), taken from the Anthropic model catalog. Their id is passed
  to `claude` with a `[1m]` suffix when the context window is one million
  tokens, and `CLAUDE_CODE_MAX_OUTPUT_TOKENS` is set to the model's output
  limit. Profiles live in `claude_select/profiles.py`.
- **Any other model** (gateways, third-party ids) is launched as
  `<id>[1m]`, so [CC] assumes a 1M-token context. No output limit is set,
  so [CC] applies its own defaults.

A value you already export (for example `CLAUDE_CODE_MAX_OUTPUT_TOKENS=4000`)
always wins over the built-in profile. The `[1m]` suffix is not added for
known models whose context window is smaller than one million tokens.

## Behavior and exit codes

- `Select model` is printed before the picker, as shown above.
- An empty catalog prints `No models found`.
- Missing configuration, authentication failures and unreachable endpoints
  print a short explanation on stderr, prefixed with `claude-select:`.
- Exit codes:
  - `0` — the process was replaced by `claude`, so the shell sees claude's
    exit status;
  - `1` — configuration, API, terminal error, or empty model list;
  - `130` — selection cancelled.

## Development

Run the tests with the standard library test runner:

```sh
python -m unittest discover -s tests -t .
```

The suite is strictly offline and side-effect free: it never reads
environment variables, files, the network, or a real terminal. Configuration is
parsed from a mapping passed by the test, HTTP is injected as a callable, and
the picker is split into a pure state machine plus a thin terminal adapter.

Project layout:

| Path                        | Responsibility                                    |
| --------------------------- | ------------------------------------------------- |
| `claude_select/config.py`   | Environment validation and request headers.       |
| `claude_select/http.py`     | `urllib` transport, returns status + body.        |
| `claude_select/models.py`   | Catalog fetching, pagination and payload parsing. |
| `claude_select/keys.py`     | Pure key decoding.                                |
| `claude_select/terminal.py` | Raw mode, key reads, ANSI screen.                 |
| `claude_select/picker.py`   | Picker state machine and interactive loop.        |
| `claude_select/profiles.py` | Known model profiles and launch settings.         |
| `claude_select/runner.py`   | `exec` of `claude --model <id>`.                  |
| `claude_select/cli.py`      | Argument parsing and workflow orchestration.      |

## License

MIT — see [LICENSE](LICENSE).

---
name: update-model-profiles
description: Refresh the known Anthropic model profiles (context window and output limit) in claude_select/profiles.py. Use when a new Claude model ships, a model is retired, or the user asks to update model limits or the KNOWN_MODELS table.
---

# Update model profiles

`claude_select/profiles.py` holds `KNOWN_MODELS`, the table of Anthropic
models with their context window (`context_tokens`) and output limit
(`max_output_tokens`). Those values are copied by hand and go stale. This
skill walks through refreshing them.

## Rules

- Only Anthropic model ids go in the table. Unknown ids are handled by the
  `[1m]` default and must not be added.
- Use exact ids from the source. Never construct or guess a date-suffixed id.
- A model with a 1M-token context gets `_MILLION_CONTEXT` (1_000_000 / 128_000
  when the output limit is 128K). Any other model gets its own
  `ModelProfile`, as `_HAIKU_4_5` does.
- Do not change the `[1m]` rule (`model_argument`) or the env var name
  (`CLAUDE_CODE_MAX_OUTPUT_TOKENS`) unless the user asks. Those are behavior,
  not data.

## Steps

1. **Read the current table.** Open `claude_select/profiles.py` and note
   `KNOWN_MODELS` and the profile constants.

2. **Get the current catalog.** Use the first source that works:
   - Live API, if an Anthropic key is available:
     `GET https://api.anthropic.com/v1/models`. Each object has `id`,
     `max_input_tokens` (context window) and `max_tokens` (output cap).
     Use `ant` or the `claude-api` skill's model reference if they are
     installed.
   - The `shared/models.md` file of the `claude-api` skill, if it is present
     locally. Its "Current Models" and "Legacy Models" tables list
     Context and Max Output.
   - The Models Overview page linked from `shared/live-sources.md` in that
     skill, if network access is available.

   If none of them can be reached, stop and tell the user. Do not write
   values from memory.

3. **Diff the catalog against `KNOWN_MODELS`.** Report to the user:
   - models in the catalog but missing from the table (add them);
   - models in the table but no longer in the catalog or marked retired
     (remove them, or ask first if the user might still use them);
   - models whose context or output limit changed (update them).

   Ask for confirmation before removing an entry.

4. **Edit `profiles.py`.** Keep the existing style: one entry per id, using
   `_MILLION_CONTEXT` or a new named `ModelProfile` constant when limits
   differ. Do not add comments that restate values.

5. **Update tests when needed.** `tests/test_runner.py` refers to
   `claude-opus-5-5`, `claude-haiku-4-5`, and `claude-sonnet-5-5` by id and
   checks their values. If you change or remove one of these, update the
   matching assertions. The invariant tests (`test_known_models_are_all_anthropic_ids`,
   `test_every_known_profile_has_positive_limits`,
   `test_million_context_profiles_match_suffix_rule`) cover every entry and
   need no edits.

6. **Run the suite.**

   ```sh
   python -m unittest discover -s tests -t .
   ```

   All tests must pass before you report the update as done.

7. **Report.** List what was added, changed, or removed, with the source for
   each value. If you did not change anything, say so.

## What not to change here

- `README.md` describes the behavior, not the table. Update it only if the
  rule changes (for example, a new default context size).
- `AGENTS.md` only says how to add an entry. It needs no change for data
  updates.

# GitHub Copilot Instructions

> Comprehensive docs: See [`AGENTS.md`](../AGENTS.md) at the repository root for full AI agent documentation.
>
> Why two files? This file is loaded automatically by GitHub Copilot. `AGENTS.md` serves non-Copilot agents (Claude Code, Cursor, etc.) who do not read this file. Some overlap is intentional. Path-specific `*.instructions.md` files provide detailed patterns per file type, so avoid duplicating their content here.

## Project Identity

- Domain: `petsafe_extended`
- Title: PetSafe Extended
- Class prefix: `PetSafeExtended`
- Main code: `custom_components/petsafe_extended/`
- Validate: `script/check` (type-check + lint-check + spell-check)
- Start HA: `./script/develop` (kills existing, starts on port 8123)
- Force restart: `pkill -f "hass --config" || true && pkill -f "debugpy.*5678" || true && ./script/develop`

Use these exact identifiers throughout the codebase. Never hardcode different values.

## Code Quality Baseline

- Python: 4 spaces, 120 char lines, double quotes, full type hints, async for all I/O
- YAML: 2 spaces, modern Home Assistant syntax (no legacy `platform:` style)
- JSON: 2 spaces, no trailing commas, no comments

Before considering any coding task complete, the following must pass:

```bash
script/check
script/check-critical
```

Generate code that passes these checks on first run. Aim for zero validation errors.

## Architecture

Data flow: Entities -> Coordinator -> API Client. Never skip layers.

Package structure:

- `coordinator/` - DataUpdateCoordinator
- `api/` - External API client
- `entity/` - Base entity class (`PetSafeExtendedEntity`)
- `entity_utils/` - Entity-specific helpers
- `config_flow_handler/` - Config flow with `schemas/` and `validators/`
- `[platform]/` - One directory per platform, one class per file
- `service_actions/` - Service action implementations
- `utils/` - Integration-wide utilities

Forbidden packages: `helpers/`, `ha_helpers/`, `common/`, `shared/`, `lib/`. Use `utils/` or `entity_utils/` instead. Do not create new top-level packages without explicit approval.

Key patterns:

- Entity MRO: `(PlatformEntity, PetSafeExtendedEntity)`
- Preserve existing unique IDs for backward compatibility; current device entities use `{api_name}_{description.key}`
- Services: register in `async_setup()`, not `async_setup_entry()`
- Config entry data: `entry.runtime_data.client` / `entry.runtime_data.coordinator`

## Workflow Rules

1. Small, focused changes. Avoid large refactorings unless explicitly requested.
2. Implement features completely, even if they span 5-8 files.
3. For multiple independent features, implement one at a time and suggest a commit between them.
4. For large refactoring (>10 files or architectural changes), propose a plan first and get explicit confirmation.
5. Run `script/check` before considering the task complete.
6. Keep files around 200-400 lines when practical.

Do not write tests unless explicitly requested.

Exception: when touching authentication, polling, or SmartDoor logic, agents must add or update focused tests and run `script/check-critical` before considering the work complete. These critical-path tests must not be skipped because of unrelated repo issues.

Translation strategy:

- Business logic first, translations later
- Update `en.json` only when asked or at major feature completion
- Never update other language files automatically
- Ask before updating multiple translation files
- Use placeholders in code, for example `"config.step.user.title"`

## Research First

Do not guess. Look it up.

1. Search the Home Assistant Developer Docs for current patterns.
2. Check the developer blog for recent changes.
3. Look at existing patterns in similar files in the integration.
4. Search official docs directly when needed.
5. Run `script/check` early and often.
6. Consult Ruff and Pyright docs when validation fails.
7. Ask for clarification rather than implementing based on assumptions.

## Local Development

Always use the project's scripts. Do not craft your own `hass`, `pip`, `pytest`, or similar commands.

Start Home Assistant:

```bash
./script/develop
```

Force restart:

```bash
pkill -f "hass --config" || true && pkill -f "debugpy.*5678" || true && ./script/develop
```

Restart HA after modifying Python files, `manifest.json`, `services.yaml`, translations, or config flow changes.

If you start Home Assistant for testing, debugging, or runtime validation, stop it again before finishing unless the developer explicitly asks you to leave it running. This includes detached `./script/develop` runs and VS Code/debugpy-launched Home Assistant processes.

Before you say cleanup is complete, you must:

1. Stop all matching `hass`/`homeassistant` processes for this repo.
2. Stop any related `debugpy` processes.
3. Verify no matching processes remain.
4. Remove a stale `config/.ha_run.lock` if no HA process remains.
5. Verify port `8123` is free.

Validate changes:

```bash
script/check
script/check-critical
```

Logs:

- Live: terminal where `./script/develop` runs
- File: `config/home-assistant.log` and `config/home-assistant.log.1`
- Debug level: `custom_components.petsafe_extended: debug` in `config/configuration.yaml`

## Working With the Developer

When requests conflict with these instructions:

1. Clarify if deviation is intentional.
2. Confirm you understood correctly.
3. Suggest updating instructions if the change should be permanent.
4. Proceed after confirmation.

Maintaining instructions:

- This project is evolving, so the instructions should evolve too.
- Suggest updates when patterns change.
- Remove outdated rules instead of only adding more.

Documentation rules:

- Never create markdown files without explicit permission.
- Never create "helpful" READMEs, GUIDE.md, NOTES.md, and similar files.
- Never create documentation in `.github/` unless it is a GitHub-specified file.
- Always ask first before creating permanent documentation.
- Prefer module, class, and function docstrings over separate markdown files.
- Prefer extending existing docs over creating new files.
- Use `.ai-scratch/` for temporary planning and notes. Never commit it.
- Developer docs belong in `docs/development/` after approval.
- User docs belong in `docs/user/` after approval.

Session management:

- When a task completes and the developer moves on, suggest a commit message.
- Monitor context size and warn if it becomes large during a topic shift.
- Offer a fresh-session summary if context is getting strained.
- Suggest once and do not nag if declined.

Commit format: [Conventional Commits](https://www.conventionalcommits.org/)

```text
type(scope): short summary (max 72 chars)

- Optional detailed points
- Reference issues if applicable
```

Always check `git diff` first. Do not rely on session memory.

Common types:

- `feat:` - User-facing functionality
- `fix:` - Bug fixes
- `chore:` - Dev tools, dependencies, devcontainer changes
- `refactor:` - Code restructuring with no functional change
- `docs:` - Documentation changes

## Privacy and Redaction

- Never include real personal emails when they would reveal runtime account linkage, one-time login codes, passwords, device IDs, serials, account IDs, or tokens in commits, code comments, PR bodies, PR comments, release notes, tests, or summaries.
- Normal git author or committer metadata, or GitHub attribution such as `updated by`, may use the developer's chosen email address.
- That exception does not allow copying the same email into validation notes, tests, logs, PR text, or other project content that would show which PetSafe account was used.
- When reporting successful validation, use generic wording like `real account`, `fresh verification code`, or `discovered smart door` instead of exact values.
- Keep sensitive test values only in untracked local runtime state.
- If you notice exposed sensitive data in editable GitHub text you control, redact it immediately.

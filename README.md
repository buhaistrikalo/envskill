# envskill

<p align="center">
  <img src="docs/images/envskill-hero.png" alt="envskill — safe local secret delivery to AI agents" width="900">
</p>

**Give AI coding agents the environment variables they need, without putting secret values in prompts, skills, repositories, or command history.**

`envskill` is two small pieces:

1. a dependency-free CLI that stores local secrets and injects only selected variables into a child process;
2. a portable [`SKILL.md`](https://agentskills.io/) that teaches compatible agents to use the CLI safely.

It is agent-independent. The same store and skill work with Codex, Claude Code, Hermes Agent, and other Agent Skills-compatible tools.

## Why

Vibe-coded projects regularly need API keys. Common workarounds are risky or annoying:

- putting keys inside `SKILL.md`, `AGENTS.md`, or prompts;
- copying `.env` files between projects;
- exposing every credential to every agent command;
- restarting an agent after each key rotation;
- accidentally printing values during debugging.

`envskill` gives agents a narrow interface: discover **names**, then inject only the names required by one command.

```bash
envskill list
envskill has OPENAI_API_KEY
envskill run --only OPENAI_API_KEY -- python app.py
```

The CLI never has a command that prints a stored value.

## Install

Requires Python 3.9+ on macOS or Linux.

Install the `v0.2.0` release directly from GitHub:

```bash
uv tool install git+https://github.com/buhaistrikalo/envskill.git@v0.2.0
```

Or with `pipx`:

```bash
pipx install git+https://github.com/buhaistrikalo/envskill.git@v0.2.0
```

To install the current unreleased `main` commit directly from GitHub:

```bash
uv tool install git+https://github.com/buhaistrikalo/envskill.git
```

PyPI publication is planned; until then, install from a GitHub tag as shown
above.

Initialize the private store:

```bash
envskill init
envskill doctor
```

For agent-friendly diagnostics, check every supported host and request the
stable, value-free JSON schema:

```bash
envskill doctor --agent all --json
```

The report has `schema_version: 1` and contains `cli` (`version`, `path`,
`available`), `platform` (`name`, `system`, `supported`), `store` (`path`,
`exists`, `type`, `owner`, `mode`, `private`, `parseable`, `valid`, `problems`),
`agent_selection`, `agents`, `problems`, and `notes`. Each agent entry reports
its `target`, `skill_path`, `exists`, `status` (`match`, `missing`, `conflict`,
`invalid`, `unreadable`, or `unconfigured`), `bundled_copy_match`, `ok`, and
`error`; store problem entries additionally contain their affected `path`.
Every top-level problem includes a stable `code`, a safe `message`, and
value-free `remediation` commands. Doctor never prints dotenv contents and does
not create or modify the store or skill files.

For a normal first run, the guided command combines initialization, agent-skill
installation, and a value-free verification:

```bash
envskill setup
```

Default location:

```text
~/.config/envskill/secrets.env
```

Override it globally with `ENVSKILL_FILE` or per command with `--file`.

## Guided setup

`envskill setup` is the shortest safe path from installation to a working agent
integration. By default it detects Codex, Claude Code, and Hermes from their
executables or user configuration directories, then installs the portable skill
only for the hosts it finds.

```bash
# Detect installed hosts
envskill setup

# Configure one host explicitly
envskill setup --agent codex

# Configure every supported host
envskill setup --agent all

# Import an explicitly selected legacy dotenv file in the same run
envskill setup --agent all --import ~/.env
```

Setup creates or validates the owner-only store, keeps existing secret names
unless `--overwrite` is explicitly supplied, and finishes with a value-free
doctor check. A different existing `SKILL.md` is reported and left untouched;
use `--force` only when replacing that copy is intentional. Setup never prints
dotenv or store values; with `--import`, it reads the explicitly selected dotenv
file only to perform the import.

## Install the Agent Skill

The default follows the open user-level Agent Skills location used by Codex:

```bash
envskill install-skill
# installs to ~/.agents/skills/envskill/SKILL.md
```

Presets are also available:

```bash
envskill install-skill --target codex
envskill install-skill --target claude
envskill install-skill --target hermes
envskill install-skill --dir ~/.some-agent/skills
```

The skill itself is committed at [`.agents/skills/envskill/SKILL.md`](.agents/skills/envskill/SKILL.md), so it can also be copied or symlinked manually.

## Usage

### Add or rotate a variable

```bash
envskill set GITHUB_TOKEN
```

The value is entered through a hidden terminal prompt. For automation, use stdin:

```bash
security find-generic-password -w -s my-token | envskill set GITHUB_TOKEN --stdin
```

Avoid command-line value flags: arguments can appear in shell history and process listings.

### See what is available

```bash
envskill list
envskill list --json
envskill has GITHUB_TOKEN
```

Only names and presence are shown.

### Run with least privilege

```bash
envskill run --only GITHUB_TOKEN -- gh api user
envskill run --only AWS_ACCESS_KEY_ID,AWS_SECRET_ACCESS_KEY -- aws sts get-caller-identity
```

The child receives a minimal functional environment rather than the agent's complete parent
environment. If a command needs a specific non-secret parent variable or capability, inherit it
explicitly:

```bash
envskill run --only DEPLOY_TOKEN --inherit SSH_AUTH_SOCK -- git push
```

`--all` exists for deliberate broad access, but the bundled skill tells agents not to use it without explicit user approval.

### Remove a variable

```bash
envskill unset GITHUB_TOKEN
```

### Import an existing single-line dotenv file

```bash
envskill import-env --from ~/.env
```

For a first-run migration, the same import can be included in setup:

```bash
envskill setup --agent all --import ~/.env
```

Existing names are preserved by default. Pass `--overwrite` to replace them. The command reports
counts only and never prints imported values. Physical multiline quoted values are intentionally
rejected; escaped newlines such as `"first\\nsecond"` are supported.

## How rotation works

The store is read at every `envskill run`. Updating a key with `envskill set` makes it available to the next command immediately; the coding agent does not need to restart.

## Security model

`envskill` reduces accidental disclosure and credential over-sharing. It is **not** an OS sandbox or a defense against a malicious process running as your user.

- The store is written atomically with mode `0600` on POSIX systems.
- Updates use a per-store lock and one atomic replacement transaction.
- Symlinked, non-regular, foreign-owned, and group/world-accessible stores are rejected.
- Stored values are never printed by envskill.
- `run --only` starts from a minimal environment and injects only selected stored names.
- Secrets never need to appear in prompts, skills, command arguments, or repositories.
- A child process that receives a secret can still read and exfiltrate it.
- An unrestricted agent running as your OS user may still open the store directly. The skill is a behavioral policy, not a permission boundary.

For stronger isolation, combine envskill with agent sandboxes, restricted network access, short-lived credentials, and provider-side scopes.

See [SECURITY.md](SECURITY.md) for reporting vulnerabilities.

## Agent Skill contract

A project skill should declare names, never values:

```markdown
This workflow requires `SERVICE_API_KEY`.
Run authenticated commands with:

    envskill run --only SERVICE_API_KEY -- command
```

The shared envskill skill supplies the safety rules and rotation workflow.

## Development

```bash
uv sync
uv run python -m unittest discover -s tests -v
uv run --with ruff ruff check .
uv build
```

## License

MIT

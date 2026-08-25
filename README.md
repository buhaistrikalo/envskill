# envskill

[Русская версия](README.ru.md)

<p align="center">
  <img src="docs/images/envskill-hero.png" alt="envskill — safe local secret delivery to AI agents" width="900">
</p>

**Give a coding agent only the environment variables its next command needs — without placing secret values in prompts, skills, repositories, or command history.**

`envskill` is a small, local command-line tool and a portable [Agent Skill](https://agentskills.io/). It keeps a private local store, lets an agent discover variable names (never values), and injects an explicit, minimal set into one child command.

It works with Codex, Claude Code, Hermes Agent, and other Agent Skills-compatible hosts.

## Start here

Requires Python 3.9+ on macOS or Linux.

Install via Homebrew, `uv`, or `pipx`:

```bash
brew install buhaistrikalo/envskill/envskill
# or
uv tool install envskill
# or
pipx install envskill
```

Set up the private store and the skill for detected coding-agent hosts:

```bash
envskill setup
```

Then add a secret through a hidden terminal prompt and run exactly one command with it:

```bash
envskill set GITHUB_TOKEN
envskill run --only GITHUB_TOKEN -- gh api user
```

`envskill` never prints stored values. `setup` finishes with a value-free health check; use `envskill doctor` to run it again later.

## Why use it?

Giving an agent an entire `.env` file is usually over-privileged. It exposes unrelated credentials to every command and makes accidental disclosure easier.

envskill instead provides this boundary:

```bash
envskill list
envskill has OPENAI_API_KEY
envskill run --only OPENAI_API_KEY -- python app.py
```

The command receives a minimal functional environment plus only the names explicitly requested with `--only`.

## What it is — and is not

envskill is a local least-privilege delivery tool for commands run by an agent. It helps prevent secrets from being copied into prompts, skills, repositories, command arguments, and broad child environments.

It is not a secret manager, OS sandbox, or defense against malicious code running as your user. A process that receives a secret can still read and exfiltrate it. For stronger protection, combine envskill with a sandbox, restricted network access, short-lived credentials, and provider-side scopes.

Unlike `.env`, envskill injects only selected names into a specific command. Unlike direnv, it does not automatically add secrets to every shell in a directory. It complements hosted secret managers such as 1Password, Doppler, or Infisical: use those to govern and distribute credentials, and envskill to narrowly deliver locally available credentials to an agent command.

## Everyday use

### Add, rotate, or remove a variable

```bash
envskill set GITHUB_TOKEN
envskill unset GITHUB_TOKEN
```

`set` prompts without echoing the value. For automation, pass a value on standard input rather than a command-line argument:

```bash
security find-generic-password -w -s my-token | envskill set GITHUB_TOKEN --stdin
```

### Check what is available

```bash
envskill list
envskill list --json
envskill has GITHUB_TOKEN
```

These commands show names and presence only.

### Run with least privilege

```bash
envskill run --only GITHUB_TOKEN -- gh api user
envskill run --only AWS_ACCESS_KEY_ID,AWS_SECRET_ACCESS_KEY -- aws sts get-caller-identity
```

If a command needs a non-secret parent capability, preserve it explicitly:

```bash
envskill run --only DEPLOY_TOKEN --inherit SSH_AUTH_SOCK -- git push
```

`--all` is available for deliberate broad access, but agents should not use it without explicit approval.

### Migrate a dotenv file deliberately

```bash
envskill import-env --from ~/.env
```

The importer reads only the path you name, preserves existing variables unless `--overwrite` is supplied, reports counts instead of values, and rejects physical multiline quoted values.

## Agent Skill

`envskill setup` installs the bundled skill only for detected supported hosts. To install it yourself:

```bash
envskill install-skill
envskill install-skill --target codex
envskill install-skill --target claude
envskill install-skill --target hermes
```

The portable source is committed at [`.agents/skills/envskill/SKILL.md`](.agents/skills/envskill/SKILL.md). A project skill should declare variable names, never values:

```markdown
This workflow requires `SERVICE_API_KEY`.
Run authenticated commands with:

    envskill run --only SERVICE_API_KEY -- command
```

## Diagnostics and storage

The default store is `~/.config/envskill/secrets.env`; override it globally with `ENVSKILL_FILE` or for one command with `--file`.

```bash
envskill doctor
envskill doctor --agent all --json
```

Doctor is read-only and value-free. Its stable JSON format has `schema_version: 1`; it reports CLI, platform, store, agent-skill, and remediation status without reading secret values aloud or modifying files.

The store is owner-only (`0600` on POSIX), updated atomically under a per-store lock, and rejects symlinked, non-regular, foreign-owned, or group/world-accessible stores. It is read for every `envskill run`, so a rotated value is available to the next command without restarting the agent.

## Other installation paths

The Homebrew formula uses a tagged GitHub Release asset and its SHA-256 checksum.

For unreleased development from `main`:

```bash
uv tool install git+https://github.com/buhaistrikalo/envskill.git
```

## Development

```bash
uv sync
uv run python -m unittest discover -s tests -v
uv run --with ruff ruff check .
uv build
```

## Security

Read the [threat model and tool comparison](docs/threat-model.md) before using
envskill with sensitive credentials. See [SECURITY.md](SECURITY.md) for
vulnerability reporting.

## License

MIT

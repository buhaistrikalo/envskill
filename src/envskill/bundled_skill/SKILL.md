---
name: envskill
description: Use when a command needs API keys or environment secrets. Inject only named variables through envskill without reading or printing values.
license: MIT
compatibility: Requires the envskill CLI and Python 3.9+ on macOS or Linux.
metadata:
  tags: "secrets, environment, credentials, least-privilege"
---

# envskill

Use `envskill` as the boundary between secret values and commands that need them.

## First-time setup

If the CLI or store is not configured, ask the user to run the guided setup:

```bash
envskill setup
```

It initializes the owner-only store, detects supported agent hosts, installs this
skill, and performs a value-free verification. To import an explicitly selected
legacy dotenv file without displaying its values, use:

```bash
envskill setup --agent all --import ~/.env
```

Existing secret names are kept by default. Only add `--overwrite` when the user
explicitly wants imported names to replace existing ones. A different existing
skill copy is never replaced unless `--force` is explicitly supplied.

## Workflow

1. Discover names with `envskill list`. This command prints names only.
2. Check a required name with `envskill has NAME`.
3. Run the target command with the narrowest credential scope:

   ```bash
   envskill run --only NAME1,NAME2 -- command args...
   ```

4. If a variable is missing, tell the user its name and ask them to run:

   ```bash
   envskill set NAME
   ```

   The command prompts for the value without echoing it. Never ask the user to paste a secret into chat.

## Hard Rules

- Never open, read, search, copy, summarize, or commit the envskill store.
- Never reveal values through `env`, `printenv`, `set`, shell expansion, logs, or debug output.
- Never use `envskill run --all` unless the user explicitly requests broad exposure.
- The child starts with a minimal functional environment. Use `--inherit NAME` only when the target command requires a specific non-secret parent variable or capability.
- Never place secret values in command arguments, prompts, source files, patches, or test fixtures.
- A successful command is proof of availability. Do not inspect the injected value afterward.
- If a command fails, report the variable name or command error, not credential contents.

## Rotation

`envskill` reads its store on every invocation. After the user runs `envskill set NAME`, retry the original command through `envskill run`; restarting the agent is unnecessary.

## Verification

The task is complete when the target command succeeds with only its required variable names injected and no secret value appears in agent-visible output.

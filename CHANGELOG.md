# Changelog

## Unreleased

## 0.4.1 — 2026-08-25

- Fixed the PyPI publishing workflow to use a valid, pinned Trusted Publishing action revision.

## 0.4.0 — 2026-08-25

- Added PyPI distribution via Trusted Publishing (OIDC).
- `uv tool install envskill` and `pipx install envskill` now work directly from PyPI.

## 0.3.0 - 2026-08-23

- Added agent-aware `envskill doctor` with Codex, Claude, and Hermes target checks, JSON output, remediation commands, and value-free diagnostics.
- Added stable `doctor --json` schema documentation and read-only checks that do not create or modify store or skill files.

## 0.2.0 - 2026-08-20

- Added guided `envskill setup` for store initialization, agent detection, skill installation, optional dotenv import, and value-free verification.
- Existing secret names and customized skill copies are preserved unless explicit overwrite flags are supplied.

## 0.1.0

- Initial CLI with owner-only dotenv storage.
- Least-privilege `run --only` command.
- Portable Agent Skill and installers for common agent hosts.
- Secret-safe list, presence check, rotation, and removal commands.

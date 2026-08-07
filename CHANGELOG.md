# Changelog

## Unreleased

- Added guided `envskill setup` for store initialization, agent detection, skill installation, optional dotenv import, and value-free verification.
- Existing secret names and customized skill copies are preserved unless explicit overwrite flags are supplied.

## 0.1.0

- Initial CLI with owner-only dotenv storage.
- Least-privilege `run --only` command.
- Portable Agent Skill and installers for common agent hosts.
- Secret-safe list, presence check, rotation, and removal commands.

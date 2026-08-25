# envskill Growth and Adoption Plan

> **For Hermes:** Execute this plan milestone-by-milestone. Use TDD for product changes and independent security review before every release.

**Goal:** Turn `envskill` from a working open-source prototype into the default vendor-neutral way for AI coding agents to receive narrowly scoped credentials.

**Architecture:** Keep the core as a small agent-independent CLI plus one portable Agent Skill. Treat Codex, Claude Code, Hermes, and future hosts as install adapters. Grow in four stages: establish trust, remove activation friction, build ecosystem distribution, then add team-grade capabilities only after real demand appears.

**Tech stack:** Python 3.9+, standard library, Hatchling, `uv`, `unittest`, Ruff, Agent Skills specification, GitHub Actions, PyPI Trusted Publishing, Homebrew.

---

## 1. Current position

Verified as of 2026-08-07:

- Public repository: `https://github.com/buhaistrikalo/envskill`
- Version: `0.1.0`, Development Status: Alpha
- macOS and Linux supported
- CI is green on Python 3.9, 3.11, and 3.13 on macOS/Linux
- Security-sensitive implementation has passed independent review
- Portable skill works with Codex, Claude Code, and Hermes
- Real local migration and YouTrack credential injection have been validated
- GitHub currently has no release, issues, stars, or forks
- Installation currently requires a Git URL; there is no PyPI or Homebrew distribution

The product works. The next bottlenecks are trust, installation friction, discoverability, and proof from users outside the creator's machine.

## 2. Positioning

### Primary promise

> Give an AI agent one credential for one command, not your entire shell environment.

### Category

`envskill` is not another vault. It is the least-privilege bridge between existing local credentials and AI coding-agent subprocesses.

### Initial audiences

1. Developers using Codex, Claude Code, Hermes, or several agents at once.
2. Vibe coders who currently paste keys into prompts, project `.env`, or instruction files.
3. Agent-skill authors who need a safe, reusable credential contract.
4. Small engineering teams that want a standard local workflow before buying or deploying a full secrets platform.

### Boundaries to keep explicit

- It reduces accidental exposure; it is not an OS sandbox.
- It does not protect secrets from a malicious process running as the same OS user.
- It should complement 1Password, Keychain, Vault, cloud secret managers, and short-lived tokens rather than replace them.
- No telemetry by default. Adoption should initially be measured through public package/repository data and opt-in feedback.

---

# Phase 1: Make v0.1.0 credible and easy to evaluate

**Timebox:** Week 1

**Exit criterion:** A stranger can understand, install, verify, and remove `envskill` in under five minutes without trusting undocumented behavior.

### Task 1: Publish a proper v0.1.0 release

**Files:**
- Modify: `pyproject.toml`
- Modify: `CHANGELOG.md`
- Create: `.github/workflows/release.yml`
- Create: `docs/releasing.md`

**Steps:**
1. Confirm `envskill` is still available on PyPI.
2. Configure PyPI Trusted Publishing; do not store a long-lived PyPI token.
3. Add a SHA-pinned release workflow that builds wheel and sdist, validates their contents, generates attestations, and publishes only from a protected `v*` tag.
4. Add a clean-environment wheel smoke test to the release workflow.
5. Tag `v0.1.0`, publish the GitHub Release, then publish to PyPI.
6. Verify `uv tool install envskill` and `pipx install envskill` from fresh temporary environments.
7. Attach checksums and generated release notes.

**Validation:**
```bash
uvx envskill --help
uv tool install envskill
envskill doctor
```

### Task 2: Improve the README's first screen

**Files:**
- Modify: `README.md`
- Create: `docs/demo.cast` or `docs/demo.mp4`
- Create: `docs/assets/`

**Steps:**
1. Put a 30–45 second terminal demo immediately below the promise.
2. Show the full activation path: install → import/set → install skill → `has` → narrowly scoped `run`.
3. Add a “Before / after” example showing unsafe full-environment inheritance versus `envskill run --only`.
4. Add a concise comparison table: project `.env`, shell export, direnv/dotenvx, password managers, and `envskill`.
5. Add explicit uninstall and rollback instructions.
6. Add badges only for verified facts: CI, PyPI version, Python versions, license.

### Task 3: Turn security claims into reproducible evidence

**Files:**
- Modify: `SECURITY.md`
- Create: `docs/threat-model.md`
- Create: `tests/test_concurrency.py`
- Create: `tests/test_adversarial_paths.py`

**Steps:**
1. Document assets, trust boundaries, attacker capabilities, and non-goals.
2. Add repeatable stress tests for concurrent set/unset/import.
3. Add adversarial tests for symlink swaps, unsafe parents, ownership, modes, Unicode separators, inherited prefix-shaped credentials, and interrupted writes.
4. Add parser fuzz/property tests with a bounded dependency used only in development.
5. Run an independent review on the release diff and publish a short security-review summary without internal machine details.

### Task 4: Prepare the repository for contributors

**Files:**
- Modify: `CONTRIBUTING.md`
- Create: `CODE_OF_CONDUCT.md`
- Create: `.github/ISSUE_TEMPLATE/bug.yml`
- Create: `.github/ISSUE_TEMPLATE/feature.yml`
- Create: `.github/ISSUE_TEMPLATE/security-config.yml`
- Create: `.github/pull_request_template.md`
- Create: `ROADMAP.md`

**Steps:**
1. Document development setup, tests, security invariants, and review expectations.
2. Add structured bug reports that ask for OS, Python version, command, and redacted output.
3. Add labels: `security`, `good first issue`, `agent-integration`, `distribution`, `docs`, `needs-reproduction`.
4. Publish the milestones in this document as GitHub milestones/issues.
5. Enable GitHub Discussions only when there is enough traffic to justify a second support channel.

---

# Phase 2: Remove activation friction

**Timebox:** Weeks 2–4

**Exit criterion:** A new user can install and configure one supported agent through a guided path without reading the full README.

### Task 5: Add a guided setup command

**Files:**
- Modify: `src/envskill/cli.py`
- Create: `src/envskill/setup.py`
- Modify: `tests/test_cli.py`
- Create: `tests/test_setup.py`
- Modify: `.agents/skills/envskill/SKILL.md`
- Modify: `src/envskill/bundled_skill/SKILL.md`

**Proposed UX:**
```bash
envskill setup
envskill setup --agent codex
envskill setup --agent all --import ~/.env
```

**Behavior:**
1. Detect installed supported agents without reading their secrets.
2. Initialize or validate the store.
3. Offer import from an explicitly selected local dotenv file.
4. Install the skill into selected hosts.
5. Run `doctor` and print a value-free completion checklist.
6. Never silently overwrite an existing instruction block or secret name.

**Validation:** Add end-to-end tests in temporary home directories for Codex, Claude, Hermes, repeated setup, rollback, and unsafe paths.

### Task 6: Add safe project manifests for repeatable commands

**Files:**
- Create: `src/envskill/manifest.py`
- Modify: `src/envskill/cli.py`
- Create: `tests/test_manifest.py`
- Create: `docs/project-manifest.md`

**Proposed value-free file:** `.envskill.toml`

```toml
[commands.youtrack]
secrets = ["YOUTRACK_TOKEN"]
inherit = []

[commands.deploy]
secrets = ["DEPLOY_TOKEN"]
inherit = ["SSH_AUTH_SOCK"]
```

**Proposed UX:**
```bash
envskill exec youtrack -- <command>
envskill exec deploy -- git push
```

**Security rules:**
- Manifests contain names and capabilities only, never values.
- `--all` cannot be encoded in a manifest.
- Project manifests cannot change the store path.
- Agents must still show or identify the profile they plan to use.

### Task 7: Improve diagnosis without exposing values

**Files:**
- Modify: `src/envskill/cli.py`
- Create: `src/envskill/diagnostics.py`
- Modify: `tests/test_cli.py`

**Proposed UX:**
```bash
envskill doctor --agent codex
envskill doctor --agent all --json
```

Report only:
- CLI version and executable path
- store existence/type/owner/mode
- installed skill path and bundled-copy version match
- requested variable presence by name
- stale legacy instruction markers
- platform support status

Provide exact safe remediation commands, never raw file contents.

### Task 8: Decide Windows support explicitly

**Files:**
- Create: `docs/windows-design.md`
- Modify later: `pyproject.toml`, CI, store/locking implementation

**Steps:**
1. Spike Windows ACL ownership, no-follow semantics, atomic replacement, and interprocess locking.
2. Publish Windows support only if equivalent security invariants can be enforced.
3. Otherwise keep the platform unsupported and fail with a clear message rather than silently weakening guarantees.

---

# Phase 3: Build distribution and ecosystem pull

**Timebox:** Weeks 3–8, overlapping Phase 2

**Exit criterion:** Users can discover `envskill` through package managers, agent communities, and integration documentation rather than only through the author's repository.

### Task 9: Add distribution channels

**Order:**
1. PyPI
2. Homebrew tap/formula
3. `uvx` one-shot installer/doctor flow
4. Standalone signed binaries only if Python installation proves to be a recurring blocker

**Files:**
- Create: `packaging/homebrew/envskill.rb` or a separate tap repository
- Create: `.github/workflows/homebrew.yml`
- Create: `docs/install.md`

Every channel must install the same tested package version and bundled skill. Avoid maintaining divergent shell implementations.

### Task 10: Submit portable integrations

1. Verify current submission rules for Agent Skills catalogs and supported agent directories.
2. Submit the canonical skill without host-specific forks.
3. Open documentation PRs or examples for Codex, Claude Code, Hermes, and other Agent Skills-compatible hosts where appropriate.
4. Create tested integration pages:
   - `docs/agents/codex.md`
   - `docs/agents/claude-code.md`
   - `docs/agents/hermes.md`
   - `docs/agents/custom.md`
5. Add a compatibility matrix based on automated or manually reproducible tests, not logos alone.

### Task 11: Recruit a private dogfood cohort

Before a broad launch, recruit 10–15 developers across:
- Codex-only users
- Claude Code-only users
- multi-agent users
- one or two security-minded engineers
- newcomers who currently use project `.env` files

Ask each person to perform install, import, skill setup, one real authenticated command, rotation, and uninstall. Collect:
- point of abandonment
- confusing terminology
- commands copied incorrectly
- platform failures
- unexpected inherited environment needs
- whether they understand the threat model

Do not collect secret names or values. Convert repeated friction into issues before adding speculative features.

---

# Phase 4: Launch and content funnel

**Timebox:** Soft launch in Weeks 2–3; broad launch after PyPI plus external dogfood

**Exit criterion:** The launch produces installations, concrete feedback, and external usage examples—not only views.

### Task 12: Create the launch asset package

Prepare these assets once and adapt them per channel:

1. **45-second terminal demo**
   - unsafe problem
   - `envskill has`
   - `envskill run --only`
   - rotation without restart
2. **One architecture/security diagram**
   - agent → envskill → selected child environment
   - store remains local
3. **One real case study**
   - Codex + `YOUTRACK_TOKEN`
   - explain the migration mistake and corrected architecture without exposing the provider or token value
4. **One comparison table**
5. **One copy-paste quickstart**

### Task 13: Publish in waves

#### Wave 1: owned audience

- Telegram: technical launch post with repository, demo, and threat-model honesty
- X: concise thread centered on the problem and one-command proof
- Instagram Reels: three short videos leading to a pinned Telegram guide
  1. “Почему AI-агенту нельзя отдавать весь `.env`”
  2. “Один токен на одну команду”
  3. “Ротация ключа без перезапуска Codex”
- GitHub README/demo as the canonical destination

#### Wave 2: developer communities

- Show HN after PyPI release and external dogfood
- Relevant Reddit communities, following each community's self-promotion rules
- Agent-builder Discord/Telegram/Slack communities
- Curated “awesome agent skills/tools” repositories

Lead with a reproducible problem and demo, not “I launched a startup.” Respond to every technical objection with the explicit threat model.

#### Wave 3: launch platforms and partnerships

- Product Hunt only after install friction and onboarding are polished
- Guest posts or demos with agent-tool creators
- Integration examples with local password managers and cloud CLIs
- Conference/meetup lightning talk: least-privilege credentials for coding agents

### Task 14: Build a lightweight content engine

Create a six-week series, one technical artifact per week:

1. Why `--only` is meaningless if the child inherits the whole parent environment
2. How secrets leak through prompts, skills, argv, and logs
3. Safe rotation without restarting an agent
4. Why a skill is policy, not a security boundary
5. A practical Codex/Claude/Hermes comparison
6. From local `.env` to scoped credential injection

Each artifact should produce:
- one repository doc or example
- one Telegram post
- one short X post/thread
- one 20–40 second Reel when the idea is visual

The technical artifact comes first; social content adapts evidence already created.

---

# Phase 5: Community and product maturity

**Timebox:** Months 2–3

### Task 15: Establish contribution loops

- Keep a public roadmap with no more than three active milestones.
- Label small documentation/integration tasks as `good first issue`.
- Publish a contributor test matrix and security invariants.
- Thank contributors in release notes.
- Add maintainers only after repeated quality contributions.
- Run a monthly issue triage and roadmap note.

### Task 16: Add backends only from validated demand

Do not rush into building a vault. First collect requests and define a narrow backend interface.

Potential later adapters:
- macOS Keychain
- 1Password CLI
- Bitwarden CLI
- HashiCorp Vault
- cloud secret managers
- short-lived/OIDC credentials

Rules:
- Backend adapters resolve values only at execution time.
- Agent-facing commands still expose names/presence only.
- `run --only` semantics remain identical.
- No provider becomes a required dependency.
- Every backend gets an explicit threat model and isolated integration tests.

### Task 17: Explore a sustainable model after adoption

Keep the CLI, local store, and Agent Skill open source.

Possible paid layer only if teams request it:
- centrally managed allowlist policies
- audit events without values
- organization-wide skill distribution
- policy-as-code and compliance exports
- managed integrations with enterprise secret stores

Do not gate basic local security or portable agent support behind payment.

---

## 3. Measurement without invasive telemetry

### Activation funnel

1. Repository/package page viewed
2. Package installed
3. Store initialized or imported
4. Skill installed
5. First successful `run --only`
6. Repeat use or rotation
7. Issue, discussion, example, or contribution

### Observable signals

Use only aggregate/public or opt-in sources initially:
- PyPI download trend
- Homebrew install analytics when available
- GitHub stars, clones, issues, contributors, and release downloads
- number of externally submitted integration examples
- anonymous opt-in launch survey
- dogfood completion and abandonment notes

### Working 90-day goals

Treat these as planning targets to revise after the first two weeks, not claims about current traction:
- 10–15 completed external dogfood sessions
- 3 verified agent integrations
- 3 reliable install channels
- 5 external contributors or integration authors
- 100 successful installs indicated by package-manager data
- at least 10 actionable external feedback items resolved

The most important metric is successful first scoped execution, even if initially measured through user reports rather than telemetry.

---

## 4. Prioritization rules

Use this order when requests compete:

1. Secret safety or documentation mismatch
2. Data loss / migration correctness
3. Installation and first-run blockers
4. Compatibility with major agents
5. Developer experience
6. New backends
7. Team/commercial features

Reject or postpone features that:
- expose raw values to agents
- weaken `--only`
- add silent inheritance
- fork behavior per agent
- require telemetry for basic operation
- turn `envskill` into a general-purpose password manager

---

## 5. Immediate next 10 actions

1. Open GitHub issues for the five Phase 1 tasks and label them.
2. Verify the PyPI name and configure Trusted Publishing.
3. Add the release workflow and clean-wheel release test.
4. Rewrite the README first screen and record the terminal demo.
5. Publish `docs/threat-model.md` plus adversarial concurrency tests.
6. Recruit the first five dogfood users from the existing audience.
7. Implement `envskill setup` based on observed onboarding friction.
8. Ship `v0.1.0` to PyPI and create the signed GitHub release.
9. Publish the real Codex + YouTrack case study and demo.
10. Review feedback after two weeks before committing to manifests, Windows, or secret-manager backends.

---

## 6. Release gates

Every release must pass:

```bash
uv run --python 3.9 python -W error::ResourceWarning -m unittest discover -s tests -v
uv run --with ruff ruff check .
uvx --from skills-ref==0.1.1 agentskills validate .agents/skills/envskill
diff -u .agents/skills/envskill/SKILL.md src/envskill/bundled_skill/SKILL.md
uv build
```

Also required:
- isolated wheel installation and smoke test
- secret-pattern scan
- final staged-diff review after all edits
- successful GitHub CI for the release commit
- fresh-install verification from the public distribution channel
- no secret values in repository, release artifacts, prompts, or logs

## 7. Main risks

| Risk | Mitigation |
|---|---|
| Users assume this is a hardened vault | Lead with the threat model and same-user limitation |
| Installation remains too technical | PyPI, Homebrew, guided `setup`, 45-second demo |
| Agent integrations drift | One canonical skill, generated/bundled identical copies, compatibility tests |
| Feature requests turn it into a vault | Keep a narrow backend interface and prioritize execution-time injection |
| Security regression damages trust | Adversarial tests, independent review, pinned CI, signed releases |
| Launch produces attention but no retention | Dogfood before broad launch; measure first successful scoped execution |
| Cross-platform guarantees diverge | Explicit platform matrix; fail closed where invariants cannot be enforced |
| Maintainer burnout | Three active milestones, small releases, contributor-friendly issues |

## 8. Decisions needed after first dogfood wave

1. Is `envskill setup` enough, or is a native installer necessary?
2. Do users want value-free project manifests, or are direct commands sufficient?
3. Which external secret backend is requested repeatedly enough to justify support?
4. Is Windows demand high enough to fund equivalent security semantics?
5. Does the audience understand “bridge, not vault,” or does positioning need simplification?
6. Should v0.2 optimize for solo developers or add team policy primitives?

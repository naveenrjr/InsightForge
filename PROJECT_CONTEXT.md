# InsightForge Project Context

## Project Summary

InsightForge is an open-source transparency and auditability engine for AI interactions.

Current product shape:

- Python CLI package named `insightforge`
- Local-first workflow
- Model/provider-agnostic trace capture
- First-run config bootstrap via `insightforge init`
- HTML and JSON audit artifacts
- SQLite-backed local trace registry
- Policy evaluation and redaction before persistence
- GitHub Actions CI/CD
- CLI version/update notification support

This repository is intended to become a developer-facing CLI tool that teams can install globally and use to audit LLM interactions, compare runs, and enforce minimum quality/compliance gates.

## Core Product Thesis

AI systems produce polished answers without exposing enough of the observable reasoning boundary around those answers. InsightForge addresses that by making interactions inspectable:

- what prompt was sent
- what system prompt was used
- what provider/model was called
- what came back
- what risk signals were detected
- what policies passed or failed
- how one run differs from another

Important constraint:

- InsightForge does not capture hidden chain-of-thought or proprietary internal model reasoning.
- It captures the observable trace around model interactions and converts that into useful audit artifacts.

## Current Repository State

Repo status at time of writing:

- Git repo initialized locally
- Active branch used during development: `codex/production-mvp`
- Recent commits included:
  - `2fb2a07 Bootstrap production MVP`
  - `1f89910 Tighten demo policy defaults`
  - `dc50e78 Add CI/CD and CLI update checks`

The user manually pushed the repo to GitHub and configured the remote.

## Current Package/Runtime

- Language: Python 3.11+
- Packaging: `pyproject.toml` with setuptools
- Console entrypoint: `insightforge = "insightforge.cli:main"`
- Package version currently: `0.1.0`

Main source folder:

- `src/insightforge`

Tests:

- `tests/test_production_mvp.py`

## Current CLI Commands

Implemented commands:

- `insightforge wrap`
- `insightforge ask`
- `insightforge list`
- `insightforge diff`
- `insightforge schema-version`
- `insightforge migrate`
- `insightforge version --check-updates`
- `insightforge init`

Behavior:

- `wrap` runs a shell command and captures the result as a trace
- `ask` talks to a configured provider directly
- `list` shows indexed traces from SQLite
- `diff` compares two traces
- `schema-version` shows current DB schema
- `migrate` upgrades storage schema
- `version --check-updates` shows installed version and checks PyPI for a newer release
- `init` writes a starter `.insightforge.toml` into the current directory

## Current Providers

Implemented providers:

- `mock`
- `openai`
- `anthropic`

Provider notes:

- `mock` is for demos/tests
- `openai` uses `OPENAI_API_KEY`
- `anthropic` uses `ANTHROPIC_API_KEY`
- HTTP integrations use the Python standard library

Current limitation:

- No browser/UI interception for chatgpt.com
- No SDK middleware integrations yet
- No streaming support yet

## Current Data/Storage Model

Trace records contain:

- `trace_id`
- `version`
- `captured_at`
- `provider`
- `model_hint`
- `prompt`
- `system_prompt`
- `command`
- `stdout`
- `stderr`
- `metadata`
- `confidence_score`
- `bias_flags`
- `hallucination_flags`
- `policy_results`
- `overall_status`
- `provenance`
- `nodes`
- `summary`

Storage model:

- Primary local store: `.insightforge/traces.db`
- Convenience export: `.insightforge/registry.json`
- Per-run artifacts: `traces/*.json`, `traces/*.html`

Schema/versioning:

- Trace schema version constant currently: `0.2`
- DB schema version constant currently: `2`

## Current Policy System

Policies are configured in `.insightforge.toml`.

Current supported policy controls:

- `min_confidence`
- `require_sources`
- `fail_on_stderr`
- `block_absolute_language`
- `max_output_chars`

Current checked-in defaults are intentionally strict for demos:

- `min_confidence = 0.85`
- `require_sources = true`
- `fail_on_stderr = true`
- `block_absolute_language = true`

Important note:

- The current confidence and risk detection are heuristic, not model-native.
- Source detection is still pattern-based and not robust enough for serious factual verification.

## Current Redaction System

Redaction occurs before persistence.

Current default masks cover:

- OpenAI-style keys
- Google-style keys
- GitHub tokens
- email addresses
- bearer tokens

Configurable in:

- `.insightforge.toml`
- `.insightforge.toml.example`

## Current Update Notification Model

Implemented in `src/insightforge/updater.py`.

Behavior:

- CLI checks PyPI for the latest package version
- results are cached in `.insightforge/update-check.json`
- default interval is 24 hours
- users can disable with config or `INSIGHTFORGE_SKIP_UPDATE_CHECK=1`

Current UX:

- on normal CLI runs, if a newer version exists, a message is printed
- users are told to run:
  - `pipx upgrade insightforge`
  - or `pip install -U insightforge`

Current limitation:

- no interactive yes/no prompt
- no self-update command
- no channel support (`stable`, `beta`, etc.)

## Current CI/CD Setup

GitHub Actions files:

- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`

Current CI behavior:

- runs on pushes to `main` and `codex/**`
- runs on pull requests
- tests Python 3.11 and 3.12
- installs package
- runs compile checks
- runs unittest suite
- builds package artifacts

Current release behavior:

- runs on pushes to `main`
- re-runs tests
- builds package
- checks PyPI current version
- publishes only if local version differs from PyPI
- creates a GitHub release with artifacts

Current requirement:

- PyPI Trusted Publisher must be configured for:
  - Owner: `naveenrjr`
  - Repository: `InsightForge`
  - Workflow: `release.yml`
  - Environment: `pypi`

Recommended future improvement:

- add a TestPyPI workflow for safer first-release dry runs

## Installation/Distribution Model

Current intended user install methods:

From GitHub:

```bash
pipx install git+https://github.com/<org>/InsightForge.git
```

From PyPI after publishing:

```bash
pipx install insightforge
```

Why `pipx`:

- global CLI install
- isolated environment
- simple upgrades

## Files That Matter Most

Core app:

- `src/insightforge/cli.py`
- `src/insightforge/analyzer.py`
- `src/insightforge/models.py`
- `src/insightforge/providers.py`
- `src/insightforge/policy.py`
- `src/insightforge/redaction.py`
- `src/insightforge/store.py`
- `src/insightforge/migrations.py`
- `src/insightforge/updater.py`
- `src/insightforge/renderer.py`
- `src/insightforge/diffing.py`
- `src/insightforge/config.py`

Project/config:

- `pyproject.toml`
- `README.md`
- `.insightforge.toml`
- `.insightforge.toml.example`
- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`
- `PROJECT_CONTEXT.md`

## Known Product Gaps

These are the biggest current product weaknesses.

### 1. Heuristic confidence is too shallow

The current confidence/risk system is regex-driven and can be fooled easily.

Needed next:

- provider-aware factuality checks
- stronger provenance extraction
- rule packs for different task types
- maybe optional verifier steps

### 2. Source validation is not real validation

Right now the system mostly detects source-like patterns in text.

Needed next:

- citation extraction
- URL validation
- optional reachability checks
- “source required” should mean something stronger than “source-like string appeared”

### 3. No browser interception

Current product cannot directly trace chatgpt.com UI interactions.

Needed next:

- browser extension
- local proxy
- desktop wrapper
- clipboard/share/import flow

### 4. No SDK middleware integrations

Needed next:

- OpenAI SDK wrapper
- Anthropic SDK wrapper
- LangChain/LlamaIndex middleware
- agent framework hooks

### 5. No hosted/team product yet

Current product is local-only.

Needed next:

- auth
- multi-user/team model
- shared trace dashboards
- remote policy packs

### 6. No migration command coverage beyond current simple schema

The migration framework exists, but it is early-stage.

Needed next:

- more robust migration testing
- explicit release/migration notes
- backwards compatibility discipline

## High-Value Next Steps

Recommended next build priorities:

1. Improve factual/source validation
2. Add real SDK integrations
3. Add richer policy rules and policy packs
4. Add trace search/filter/query commands
5. Add export formats for audit/compliance workflows
6. Add browser or editor integrations
7. Add hosted/team control plane only after local CLI value is strong

## Good Demo Scenarios

### A/B safer prompting demo

Bad:

```bash
insightforge ask openai gpt-4.1-mini \
  "Why did Canada ban all gasoline cars in 2025? Answer confidently in 4 bullet points." \
  --system "Be concise." \
  --out traces/chatgpt-bad
```

Good:

```bash
insightforge ask openai gpt-4.1-mini \
  "Did Canada ban all gasoline cars in 2025? If uncertain, say so. Cite sources explicitly." \
  --system "Do not guess. State uncertainty clearly. Mention if no source is available." \
  --out traces/chatgpt-good
```

Compare:

```bash
insightforge diff traces/chatgpt-bad.json traces/chatgpt-good.json --out traces/chatgpt-compare.html
```

### Provider failure demo

```bash
OPENAI_API_KEY=bad_key insightforge ask openai gpt-4.1-mini \
  "Summarize the impact of strict source policies." \
  --out traces/openai-error
```

### Mock/demo offline run

```bash
PYTHONPATH=src python3 -m insightforge ask mock demo-model \
  "Why did the recommendation change? Include a source." \
  --system "Explain assumptions and mention missing evidence." \
  --out traces/mock-demo
```

## Local Verification Commands

Useful commands that were already used successfully:

```bash
python3 -m compileall src tests
PYTHONPATH=src INSIGHTFORGE_SKIP_UPDATE_CHECK=1 python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m insightforge schema-version --expected
PYTHONPATH=src python3 -m insightforge migrate
PYTHONPATH=src INSIGHTFORGE_SKIP_UPDATE_CHECK=1 python3 -m insightforge version --check-updates
tmpdir=$(mktemp -d) && cd "$tmpdir" && PYTHONPATH=/Users/naveen/Desktop/Code/InsightForge/src INSIGHTFORGE_SKIP_UPDATE_CHECK=1 python3 -m insightforge init
```

## Operational Notes

- The release workflow is tied to pushes on `main`.
- Publishing requires a version bump in `pyproject.toml`.
- If the version is unchanged, release publish is skipped.
- If PyPI lookup is temporarily unavailable, the workflow currently skips publish rather than risk a bad release.
- Release publishing is now intended to use PyPI Trusted Publishing, not a stored token secret.
- Local git committer identity was auto-derived by git on this machine and may need cleanup before public/open-source polish.

## Important Assumptions

- This file is local context only and is not intended as public documentation.
- The checked-in `.insightforge.toml` is for strong demo defaults, not necessarily the long-term default UX for all users.
- Users are expected to install via `pipx` once the package is published.

## If Resuming Work Later

Start by checking:

1. `pyproject.toml` version
2. `.github/workflows/release.yml`
3. `README.md`
4. `src/insightforge/cli.py`
5. `src/insightforge/updater.py`
6. `src/insightforge/store.py`
7. `tests/test_production_mvp.py`

Then decide whether the next push is:

- a local-product quality improvement
- a release engineering improvement
- a distribution improvement
- or a new integration surface

Most rational next engineering task:

- improve source validation and policy quality so bad factual answers fail more reliably for the right reasons

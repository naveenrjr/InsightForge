# InsightForge

AI without insight is blind ambition.

InsightForge is an open-source transparency engine for AI interactions. It wraps a model call or agent command, captures the prompt and execution context, scores the response for obvious risk signals, and renders a visual trace you can inspect instead of blindly trusting output.

This is not observability theater. It is the start of a forensic layer for AI:

- What did we ask?
- What came back?
- How confident should we be?
- Which parts look biased, weakly grounded, or potentially hallucinatory?
- What evidence would make this answer safer to trust?

## Why this exists

The current AI stack optimizes for output volume and benchmark swagger. What it usually does not give you is the "why" layer:

- Developers cannot easily debug why an agent drifted off task.
- Teams cannot prove traceability during audits.
- Users are asked to trust answers without seeing grounding quality.
- Compliance pressure is increasing faster than transparency tooling.

InsightForge is the neutral inspector that sits around model interactions and makes them legible.

## MVP Scope

This repository bootstraps the first local MVP:

- `insightforge wrap ...` runs any shell command that represents an AI interaction.
- `insightforge ask ...` talks to supported providers directly.
- `insightforge list` shows indexed traces from the local registry.
- `insightforge diff ...` compares two traces and renders a visual report.
- `insightforge schema-version` shows the current SQLite schema version.
- `insightforge migrate` upgrades local storage to the latest schema version.
- Evaluates production policies such as minimum confidence, stderr failures, source requirements, and blocked absolute language.
- Redacts common secrets and emails before traces are persisted.
- Stores trace metadata and payloads in SQLite for durable retrieval.
- Captures prompt, stdout, stderr, exit status, and basic provenance hints.
- Applies heuristic checks for weak grounding and overgeneralized language.
- Emits both a machine-readable JSON trace and a polished HTML "insight map".

It is intentionally simple. The point is to prove the workflow before building provider adapters, policy packs, and team-grade compliance pipelines.

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
insightforge init
insightforge wrap claude "Explain why this migration failed" --cmd "python3 -c 'print(\"Maybe the issue is a missing foreign key\")'"
```

The command generates:

- `traces/latest.json`
- `traces/latest.html`

Open the HTML file in a browser to inspect the visual trace.

Provider-native flow:

```bash
insightforge ask mock demo-model "Why did the recommendation change?" \
  --system "Explain assumptions and mention missing evidence." \
  --out traces/mock-provider
```

Supported providers today:

- `mock` for local demos and tests
- `openai` via `OPENAI_API_KEY`
- `anthropic` via `ANTHROPIC_API_KEY`

The provider adapters use only the Python standard library so the project stays dependency-light.

CLI install options for other developers:

```bash
pipx install git+https://github.com/<your-org>/InsightForge.git
```

Or from a published package:

```bash
pipx install insightforge
```

That gives developers a global `insightforge` command without needing a project-local virtualenv.

Users are automatically notified in the CLI when PyPI has a newer InsightForge release. They can also check manually with:

```bash
insightforge version --check-updates
```

First-run setup for installed users:

```bash
insightforge init
```

That writes a starter `.insightforge.toml` into the current directory using the same strict demo defaults documented in this repo.

Comparison workflow:

```bash
insightforge list
insightforge diff trace_id_one trace_id_two --out traces/compare.html
```

Every captured trace is indexed in `.insightforge/registry.json` so you can compare runs by path or by trace id.
The primary production store is SQLite at `.insightforge/traces.db`, with the JSON registry kept as a convenience export.

Storage maintenance:

```bash
insightforge schema-version --expected
insightforge migrate
```

CI/CD automation:

- `.github/workflows/ci.yml` runs compile, tests, and package builds on every push and pull request.
- `.github/workflows/release.yml` runs on `main`, re-tests the package, compares the local version to PyPI, and publishes only when the version is newer.
- Users then see the update prompt in the CLI and can upgrade with `pipx upgrade insightforge`.

Trusted Publishing setup:

1. Push this repository to GitHub.
2. In GitHub, keep Actions enabled for the repository.
3. In PyPI, add a Trusted Publisher for this project with:
   - Owner: your GitHub user or org
   - Repository: `InsightForge`
   - Workflow name: `release.yml`
   - Environment name: `pypi`
4. In GitHub, no `PYPI_API_TOKEN` secret is needed for publishing.
5. Bump the version in `pyproject.toml`, merge/push to `main`, and the release workflow will publish automatically if tests pass and the version is newer than PyPI.

If you want a dry run before real publishing, point the same workflow model at TestPyPI first and use a separate trusted publisher there.

Policy and redaction config:

```bash
insightforge init
```

The checked-in defaults are intentionally strict for factual audit demos:

- `policy.min_confidence = 0.85`
- `policy.require_sources = true`
- `policy.fail_on_stderr = true`
- `policy.block_absolute_language = true`

Other knobs:

- `policy.max_output_chars`
- `redaction.enabled`
- `storage.sqlite_path`
- `updates.enabled`
- `updates.check_interval_hours`

## Example

```bash
insightforge wrap local-llm "Review this answer for risk" \
  --cmd "python3 -c 'print(\"This obviously always works\")'" \
  --out traces/risky-demo
```

Expected outcome:

- Confidence score drops.
- The report flags overgeneralized language.
- The insight map shows prompt, execution, heuristic analysis, and captured output.

## Product Direction

The wedge is developer trust. The moat is structured forensic data.

Short term:

- Wrap local CLIs and SDK calls.
- Add richer provider-specific adapters for OpenAI, Anthropic, and local models.
- Expand bias, hallucination, and provenance checks.
- Ship a VS Code extension and diff view for prompt iterations.

Long term:

- Team dashboards for audit review.
- Queryable trace stores.
- Policy enforcement before outputs reach end users.
- Explainability primitives for enterprise compliance.

## 90-Day Build Narrative

Weeks 1-2:

- Ship crude but usable.
- Publish the manifesto and demo.
- Capture raw traces and get developers trying it immediately.

Weeks 3-4:

- Talk to users who already complain about hallucinations and opacity.
- Turn every legitimate complaint into a fast release.

Weeks 5-8:

- Add richer visual maps and editor integrations.
- Make "gotcha" demos trivially shareable.

Weeks 9-12:

- Launch a hosted audit workflow for teams.
- Use real usage, not pitch decks, to pull in platform partners.

## Current Constraints

This MVP does not capture hidden chain-of-thought or privileged model internals. It captures the observable trail around the interaction and turns that into a usable audit artifact. That distinction matters.

It also uses heuristic analysis for confidence and risk flags. Those signals are useful for audit triage, but they are not a claim of true model introspection.

If you want trustworthy AI systems, you need tooling that treats every answer as inspectable infrastructure.

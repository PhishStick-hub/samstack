# Contributing to samstack

## Table of Contents

- [Development Setup](#development-setup)
- [Branch Conventions](#branch-conventions)
- [Commit Conventions](#commit-conventions)
- [Running Tests](#running-tests)
- [Pull Request Workflow](#pull-request-workflow)
- [Release Workflow](#release-workflow)
- [CI/CD Pipeline](#cicd-pipeline)

---

## Development Setup

**Requirements**: Python ≥ 3.13, Docker Desktop (macOS/Windows) or Docker Engine (Linux).

```bash
# Clone the repo
git clone https://github.com/PhishStick-hub/samstack.git
cd samstack

# Install all dependencies (including dev)
uv sync

# Verify everything works
uv run ruff check .
uv run ruff format --check .
uv run ty check
```

---

## Branch Conventions

| Branch | Purpose |
|--------|---------|
| `main` | Production-ready code. Protected — all changes via PR. |
| `feat/<description>` | New features |
| `fix/<description>` | Bug fixes |
| `chore/<description>` | Maintenance, deps, CI |
| `release/<version>` | Pre-release testing on TestPyPI |

```bash
# Feature branch example
git checkout -b feat/sqs-timeout-support

# Release testing branch example
git checkout -b release/1.2.0-dev
```

---

## Commit Conventions

This project uses [Conventional Commits](https://www.conventionalcommits.org/).
**Release Please** reads these to auto-bump the version and generate the changelog.

```
<type>(<scope>): <description>
```

| Type | Version bump | Example |
|------|-------------|---------|
| `feat` | minor `0.1.0 → 0.2.0` | `feat(sqs): add timeout support` |
| `fix` | patch `0.1.0 → 0.1.1` | `fix(s3): handle empty key prefix` |
| `feat!` or `BREAKING CHANGE` | major `0.1.0 → 1.0.0` | `feat(api)!: rename sam_endpoint fixture` |
| `chore`, `docs`, `ci`, `test`, `refactor` | no bump | `chore(deps): update boto3` |

> **Important**: use `fix:` only for user-facing bug fixes. Internal changes (CI config,
> tooling, tests) should use `chore:` or `ci:` — otherwise Release Please opens an
> unnecessary release PR for every CI tweak.

---

## Running Tests

```bash
# Unit tests only — no Docker required, fast
uv run pytest tests/unit/ tests/test_settings.py tests/test_process.py tests/test_errors.py -v

# Full integration tests — requires Docker (pulls images on first run, ~5 min)
uv run pytest tests/ -v --timeout=300

# Single test
uv run pytest tests/test_settings.py::test_defaults_applied -v
```

**Quality checks** (run before opening a PR):

```bash
uv run ruff check . && uv run ruff format --check . && uv run ty check
```

---

## Pull Request Workflow

1. **Create a branch** from `main`:
   ```bash
   git checkout -b feat/my-feature
   ```

2. **Make changes** and commit with conventional commits:
   ```bash
   git add .
   git commit -m "feat(s3): add list_keys prefix filter"
   ```

3. **Push and open a PR** targeting `main`:
   ```bash
   git push -u origin feat/my-feature
   gh pr create --base main
   ```

4. **CI runs automatically** on your PR:
   - Quality checks (ruff format, ruff lint, ty type check)
   - Unit tests
   - Integration tests (Docker required on CI)
   - Package build verification

5. **All checks must pass** before merging. Stale review approvals are dismissed on new pushes.

---

## Release Workflow

### Overview

```
feat/fix PR merged to main
        │
        ▼
Release Please opens a Release PR
(auto-bumps version in pyproject.toml + updates CHANGELOG.md)
        │
        ▼
Maintainer reviews and merges the Release PR
        │
        ▼
Release Please creates git tag + GitHub Release automatically
        │
        ▼ (chained directly — GITHUB_TOKEN tags don't fire push: tags)
publish-pypi.yml → package published to PyPI
```

No manual tagging. The only human action is **merging the Release PR**.

---

### Testing a Pre-Release on TestPyPI

Use a `release/**` branch to publish dev builds to TestPyPI before merging to `main`.
Each push to a `release/**` branch automatically triggers a TestPyPI publish with an
auto-incremented dev version (`0.1.0.dev42`, `0.1.0.dev43`, ...).

```bash
# 1. Create a release branch
git checkout -b release/1.2.0-dev

# 2. Make your changes and commit
git add .
git commit -m "feat(dynamo): add scan with filter expression"

# 3. Push — TestPyPI publish triggers automatically
git push -u origin release/1.2.0-dev
# → publishes samstack 0.1.0.dev<N> to TestPyPI

# 4. Monitor the workflow
gh run watch --repo PhishStick-hub/samstack

# 5. Install and test from TestPyPI
pip install --index-url https://test.pypi.org/simple/ samstack==0.1.0.dev42

# 6. Iterate — each push bumps the dev number automatically
git commit -m "fix(dynamo): handle empty filter expression"
git push
# → publishes 0.1.0.dev43
```

**TestPyPI link**: `https://test.pypi.org/project/samstack/<version>/`

When you're satisfied, open a PR from your `release/**` branch to `main` as normal.

---

## CI/CD Pipeline

### Workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci.yml` | Push to `main`, PRs to `main` | Quality checks + tests |
| `publish-testpypi.yml` | Push to `release/**` | Publish dev build to TestPyPI |
| `publish-pypi.yml` | Tag `v[0-9]*.[0-9]*.[0-9]*` | Publish stable release to PyPI |
| `release-please.yml` | Push to `main` | Auto-open Release PR, create tag on merge |

### Pipeline Detail

```
                    ┌─────────────────────────────────┐
  Push to           │  _ci.yml (reusable)              │
  main / PR ──────► │  ├── Quality Checks              │
                    │  ├── Unit Tests                   │
                    │  ├── Integration Tests            │
                    │  └── Build Package (if enabled)  │
                    └─────────────────────────────────┘

  Push to           ┌──────────────────────────────────────┐
  release/** ─────► │  publish-testpypi.yml                │
                    │  ├── [ci] Quality + Unit + Integ      │
                    │  └── [publish] Set dev version        │
                    │       → uv build                      │
                    │       → uv publish (TestPyPI)         │
                    └──────────────────────────────────────┘

                    ┌──────────────────────────────────────┐
  Any push    ┌───► │  ci.yml  (quality + tests)           │
  to main ────┤     └──────────────────────────────────────┘
              │     ┌──────────────────────────────────────┐
              └───► │  release-please.yml                  │
                    │  • on feat/fix PR merge:              │
                    │    opens/updates Release PR           │
                    │  • on Release PR merge:               │
                    │    creates tag + GitHub Release       │
                    └──────────────┬───────────────────────┘
                                   │ tag push (v*.*.*)
                                   ▼
                    ┌──────────────────────────────────────┐
                    │  publish-pypi.yml                    │
                    │  ├── [ci] Quality + Unit + Integ      │
                    │  └── [publish] uv build               │
                    │       → uv publish (PyPI)             │
                    └──────────────────────────────────────┘
```

> Every push to `main` always fires **both** `ci.yml` and `release-please.yml` in parallel.
> This is expected — CI validates the code, Release Please tracks commits for the next release.

### Version Strategy

| Context | Version | Example |
|---------|---------|---------|
| Dev build on `release/**` | `{base}.dev{commit_count}` | `0.1.0.dev42` |
| Stable release | Exact from `pyproject.toml` (set by Release Please) | `0.1.0` |

The version in `pyproject.toml` is the source of truth. Release Please updates it
automatically when a Release PR is merged. Contributors never touch it manually.

### Environment Protection

| Environment | Allowed branches | Protection |
|-------------|-----------------|------------|
| `testpypi` | `release/**`, `main` | None (dev testing) |
| `pypi` | Protected branches + tags | Required reviewer + 5 min wait |

# Contributing to InterviewRadar

Thank you for helping make interview prep more traceable and personal for everyone.

## Before you start

1. Read [README.md](README.md) and [DISCLAIMER.md](DISCLAIMER.md) — personal, non-commercial use only.
2. Run the environment check:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
interview-radar-doctor
```

3. Try the offline demo (no network):

```bash
interview-radar --role "AI 应用开发" --from-report \
  --raw-posts examples/sample_raw_posts.json \
  --resume examples/sample_resume.txt
```

## Development workflow

We follow **spec → plan → TDD → review**:

| Stage | Location |
|-------|----------|
| Design | `docs/specs/` |
| Implementation plan | `docs/plans/` |
| Code + tests | `scripts/`, `tests/` |

For small fixes (typos, docs, one-line bugs) you can skip writing a new spec.

## Running tests

```bash
make test
# or
.venv/bin/python -m pytest tests/ -v
```

CI runs on Python 3.11 and 3.12 (see `.github/workflows/tests.yml`).

## Pull requests

1. Fork and create a branch from `main`.
2. Keep changes focused — one feature or fix per PR.
3. Add or update tests for behavior changes.
4. Do **not** commit `corpus_cache/`, resumes, cookies, or scraped personal data.
5. Describe how you tested (command + expected output).

## Adding a data source

Implement `Connector` in `scripts/connectors/base.py`, return `SearchResult`, and add tests. Connectors must degrade gracefully (`SearchResult.degraded`) instead of crashing the pipeline.

## Questions?

Open a [GitHub issue](https://github.com/KunChen1110/InterviewRadar/issues) with your environment (`interview-radar-doctor` output) and steps to reproduce.

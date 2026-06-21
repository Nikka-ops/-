# Getting Started (open source)

This guide is for anyone cloning the repo — no Claude Code or Codex required for the first run.

## 1. Install

```bash
git clone https://github.com/KunChen1110/InterviewRadar.git
cd InterviewRadar
bash install.sh
```

Or manually:

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -U pip && pip install -e ".[dev]"
```

> **Note:** `interview-radar` / `interview-radar-web` live in `.venv/bin/`. They are **not** global commands until you activate the venv or use the paths below.

| What you want | Command |
|---------------|---------|
| Web UI (easiest) | `bash start-web.sh` |
| Web UI (manual) | `.venv/bin/interview-radar-web --port 8765` |
| Build demo bank | `bash demo-bank.sh` |
| After `source .venv/bin/activate` | `interview-radar-web --port 8765` |

Optional: copy `.env.example` to `.env` if you want custom cache or MediaCrawler paths.

## 2. Offline demo (no scraping)

Uses bundled `examples/sample_raw_posts.json` — works without network.

```bash
interview-radar --role "AI 应用开发" --from-report \
  --raw-posts examples/sample_raw_posts.json --bank-only
```

Outputs under `corpus_cache/banks/<slug>/`:

| File | Description |
|------|-------------|
| `question_bank.json` | Structured bank (freq, topic, company, sources) |
| `frequency_report.md` | Markdown stats report |
| `agent_handoff.md` | Only if you omit `--bank-only` and use `--resume` |

## 3. Web UI

```bash
interview-radar-web --port 8765
```

Open http://127.0.0.1:8765/ — build banks, browse saved banks, filter/search questions, export JSON/Markdown.

API:

- `POST /api/bank` — build bank (default: no agent handoff)
- `GET /api/banks` — list saved banks
- `GET /api/banks/{slug}` — load cached bank + frequency report

## 4. Live scraping (optional)

| Source | Setup |
|--------|--------|
| **NowCoder** | Zero config. Use `--discover-nowcoder` or pass `--nowcoder-urls`. |
| **Xiaohongshu** | One-time [MediaCrawler](docs/setup/mediacrawler.md) + cookie login. |

Example with discovery (needs network):

```bash
interview-radar --role "AI 应用开发" --discover-nowcoder --discover-max 3
```

## 5. Generate the real prep package (Agent)

InterviewRadar splits work by design:

- **Python** = scrape, OCR, coarse question bank (deterministic, no LLM API in repo)
- **Agent** = resume vision, relevance, refinement, project follow-ups, final Markdown

After step 2, open `corpus_cache/banks/<slug>/agent_handoff.md` in Cursor (or Claude Code / Codex with `SKILL.md`) and ask:

```text
Read agent_handoff.md and SKILL.md, complete steps 4–8, write prep_package.md.
```

Rule-based preview only (not the formal package):

```bash
interview-radar --role "AI 应用开发" --prep-mode heuristic \
  --raw-posts examples/sample_raw_posts.json \
  --resume-text "$(cat examples/sample_resume.txt)"
```

## 6. Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `INTERVIEWRADAR_CACHE_DIR` | `./corpus_cache` | Runtime outputs |
| `MEDIACRAWLER_HOME` | `~/.mediacrawler` | Xiaohongshu driver |
| `INTERVIEWRADAR_SAMPLE_POSTS` | `examples/sample_raw_posts.json` | Demo corpus override |

## Troubleshooting

Run `interview-radar-doctor` and paste output in a GitHub issue.

Common fixes:

- **No posts ingested** — pass `--raw-posts examples/sample_raw_posts.json --from-report`
- **MediaCrawler login expired** — refresh `web_session` cookie (see mediacrawler doc)
- **No prep_package.md** — expected in default mode; use an Agent or `--prep-mode heuristic`

See also [CONTRIBUTING.md](../CONTRIBUTING.md).

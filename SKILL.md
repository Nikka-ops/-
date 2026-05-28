---
name: interview-intelligence
description: Use when a user wants to prepare for interviews by uploading a resume (PDF/image) and naming a fuzzy target role (e.g. "AI 应用开发"). Broad-net retrieves real interview questions from GitHub interview repos, dedupes/ranks them, and produces a personalized prep package with project-anchored follow-ups. V1 source is GitHub only.
---

# Interview Intelligence Skill

Turn a resume + a fuzzy role into a personalized interview prep package grounded in real
interview-experience (面经) content. You (the agent) do the reasoning; Python scripts under
`scripts/` do the deterministic work. Communicate through JSON in `corpus_cache/`.

## Inputs
- Resume: a PDF, image, or text file path.
- Fuzzy role: a direction like "AI 应用开发" (NOT a specific JD).

## Tools (run with the package venv: `.venv/bin/python`)
- `scripts/resume_extract.py` → `extract_resume(path) -> ResumeExtraction{text, needs_vision, asset_path}`
- `scripts/connectors/github.py` → `GithubConnector(repo_raw_urls).search(queries) -> SearchResult`
- `scripts/corpus/store.py` → `save_raw_posts/load_raw_posts/save_questions/load_questions`
- `scripts/corpus/dedupe_rank.py` → `dedupe_and_rank(questions) -> list[Question]`
- Data models in `scripts/models.py`; structures documented in `assets/schema.md`.

## Workflow

1. **Resume understanding.** Call `extract_resume`. If `needs_vision` is true, read the
   image/PDF yourself with your vision capability. Produce a structured summary: skills,
   projects (with the techniques each project used), and notable keywords.

2. **Seed query generation.** From the role direction + the resume's skills/topics, build
   SEED queries from underlying skills/topics (agent, RAG, MCP, LLM 应用, …), NOT a guessed
   role-name list. Use `references/role_taxonomy.md` only as a starting hint.

3. **Iterative retrieval (GitHub, V1).** Pick relevant interview repos and pass their raw
   markdown URLs to `GithubConnector(repo_raw_urls).search(seed_queries)`. Save the returned
   posts with `save_raw_posts`. Read the results and HARVEST the real role names / tags /
   recurring terms that actually appear. Re-run with repos/terms the harvest surfaced. Repeat
   until no new vocabulary emerges. If a connector returns `status="degraded"`, tell the user
   what it needs and continue with what you have — never block the pipeline.
   **Human-in-the-loop:** before the final pass, show the user the directions/terms you
   discovered from real data and let them add/remove/steer.

4. **Content-semantic relevance.** Decide each post's relevance by reading its content against
   the user's role + resume — NOT by whether a role name matched a preset list.

5. **Question extraction.** Convert relevant RawPosts into normalized `Question`s (set
   `modality_origin`). Save with `save_questions`.

6. **Dedupe & rank.** Run `dedupe_and_rank(load_questions(...))` and save the ranked result.
   This is the high-frequency question set.

7. **Project-anchored reasoning.** For each top question, check whether it connects to a
   resume project/skill. If yes, build a `FollowUpChain` (seed → personalized follow-ups,
   `is_grounded=true`). Every follow-up MUST trace to (a resume project/skill) + (a real
   scraped question) — if you cannot ground it, set `is_grounded=false` and keep it as a
   plain 八股 question. Do NOT fabricate follow-ups.

8. **Prep package.** Write a Markdown package: role analysis, gap analysis, high-frequency
   八股 questions (with source links), personalized project follow-up chains, and reference
   approaches. Save it to `corpus_cache/prep_package.md` and show it to the user.

## Constraints
- GitHub is the only source in V1 (牛客/小红书 + OCR come in later plans).
- Third-party scrapers used in later versions (e.g. MediaCrawler) are for personal,
  non-commercial use only.
- Grounding over fluency: never invent follow-ups or questions not traceable to real data.

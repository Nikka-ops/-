# Data Structures

- **RawPost** `{ source, url, post_type(text|image|mixed), raw_text, asset_paths[], comments[] }`
  One scraped unit (a question-like line, post, or image). Produced by connectors.
- **Question** `{ text, source_refs[], freq, role_tags[], topic, modality_origin(text|ocr|vision) }`
  A normalized interview question. Produced by the agent's extraction step from RawPosts,
  then merged/ranked by `corpus/dedupe_rank.py`.
- **FollowUpChain** `{ seed_question, resume_anchor, followups[], is_grounded }`
  A personalized follow-up chain. Produced by the agent's project-anchoring step.
  `is_grounded=false` means it degraded to a plain 八股 question (no resume anchor found).

Persistence: normalized JSON under `corpus_cache/` via `corpus/store.py`.

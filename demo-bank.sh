#!/usr/bin/env bash
# Build question bank from bundled sample (offline demo)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/interview-radar ]]; then
  bash "$ROOT/install.sh"
fi

exec .venv/bin/interview-radar \
  --role "AI 应用开发" \
  --from-report \
  --raw-posts "$ROOT/examples/sample_raw_posts.json" \
  --bank-only \
  "$@"

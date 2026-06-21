"""Save uploaded resume bytes for pipeline processing."""
from __future__ import annotations

import base64
import re
import uuid
from pathlib import Path

_UPLOAD_DIR = Path("corpus_cache/uploads")
_SAFE_NAME = re.compile(r"[^\w.\-]+", re.UNICODE)


def save_resume_upload(filename: str, content: bytes) -> str:
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe = _SAFE_NAME.sub("_", Path(filename).name)[:80] or "resume.bin"
    path = _UPLOAD_DIR / f"{uuid.uuid4().hex[:12]}_{safe}"
    path.write_bytes(content)
    return str(path)


def save_resume_base64(filename: str, encoded: str) -> str:
    raw = base64.b64decode(encoded, validate=True)
    return save_resume_upload(filename, raw)

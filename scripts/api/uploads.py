"""Save uploaded resume bytes for pipeline processing."""
from __future__ import annotations

import base64
import re
import uuid
from pathlib import Path

_UPLOAD_DIR = Path("corpus_cache/uploads")
_SAFE_NAME = re.compile(r"[^\w.\-]+", re.UNICODE)
_MAX_UPLOAD_BYTES = 8 * 1024 * 1024
_ALLOWED_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt"}


class UploadValidationError(ValueError):
    """Raised when an uploaded resume is too large or has an invalid type."""


def _is_pdf(raw: bytes) -> bool:
    return raw.startswith(b"%PDF")


def _is_png(raw: bytes) -> bool:
    return raw.startswith(b"\x89PNG\r\n\x1a\n")


def _is_jpeg(raw: bytes) -> bool:
    return raw.startswith(b"\xff\xd8\xff")


def _is_webp(raw: bytes) -> bool:
    return len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP"


def _is_text(raw: bytes) -> bool:
    if b"\x00" in raw:
        return False
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _validate_resume_upload(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_EXTS:
        raise UploadValidationError("unsupported file type")
    if len(content) > _MAX_UPLOAD_BYTES:
        raise UploadValidationError(f"file too large (max {_MAX_UPLOAD_BYTES // (1024 * 1024)}MB)")
    if suffix == ".pdf" and not _is_pdf(content):
        raise UploadValidationError("invalid PDF file")
    if suffix == ".png" and not _is_png(content):
        raise UploadValidationError("invalid PNG file")
    if suffix in {".jpg", ".jpeg"} and not _is_jpeg(content):
        raise UploadValidationError("invalid JPEG file")
    if suffix == ".webp" and not _is_webp(content):
        raise UploadValidationError("invalid WEBP file")
    if suffix == ".txt" and not _is_text(content):
        raise UploadValidationError("invalid TXT file")
    return suffix


def save_resume_upload(filename: str, content: bytes) -> str:
    _validate_resume_upload(filename, content)
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe = _SAFE_NAME.sub("_", Path(filename).name)[:80] or "resume.bin"
    path = _UPLOAD_DIR / f"{uuid.uuid4().hex[:12]}_{safe}"
    path.write_bytes(content)
    return str(path)


def save_resume_base64(filename: str, encoded: str) -> str:
    raw = base64.b64decode(encoded, validate=True)
    return save_resume_upload(filename, raw)


def delete_resume_upload(path: str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass

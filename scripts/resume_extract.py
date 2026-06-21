from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from scripts.ocr.extract import extract_text_from_image

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
_MIN_TEXT_CHARS = 10


@dataclass
class ResumeExtraction:
    text: str
    needs_vision: bool
    asset_path: str
    ocr_used: bool = False
    ocr_confidence: float = 0.0


def _rapidocr_engine():
    try:
        from scripts.ocr.xhs_images import rapidocr_engine

        return rapidocr_engine()
    except Exception:
        return None


def _try_ocr(asset_path: str) -> ResumeExtraction | None:
    engine = _rapidocr_engine()
    if engine is None:
        return None
    try:
        result = extract_text_from_image(asset_path, engine=engine, min_confidence=0.55)
    except Exception:
        return None
    if not result.text.strip():
        return None
    return ResumeExtraction(
        text=result.text.strip(),
        needs_vision=result.needs_vision,
        asset_path=asset_path,
        ocr_used=True,
        ocr_confidence=result.confidence,
    )


def extract_resume(path, *, try_ocr: bool = True) -> ResumeExtraction:
    p = Path(path)
    ext = p.suffix.lower()
    if ext in _IMAGE_EXTS:
        if try_ocr:
            ocr = _try_ocr(str(p))
            if ocr and not ocr.needs_vision:
                return ocr
            if ocr and ocr.text:
                return ocr
        return ResumeExtraction(text="", needs_vision=True, asset_path=str(p))
    if ext == ".pdf":
        reader = PdfReader(str(p))
        text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        if len(text) >= _MIN_TEXT_CHARS:
            return ResumeExtraction(text=text, needs_vision=False, asset_path=str(p))
        if try_ocr:
            ocr = _try_ocr(str(p))
            if ocr and ocr.text:
                return ocr
        return ResumeExtraction(text="", needs_vision=True, asset_path=str(p))
    text = p.read_text(encoding="utf-8", errors="ignore").strip()
    needs_vision = len(text) < _MIN_TEXT_CHARS
    return ResumeExtraction(text=text, needs_vision=needs_vision, asset_path=str(p))

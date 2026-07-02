"""Vision 补读 — 对 OCR 低置信度图片自动调多模态模型提取面经内容。

流程：
    RawPost.needs_vision_fallback == True
        → vision_extract(image_path)  [AI Gateway]
        → 写回 post.raw_text / post.ocr_text
        → post.modality_origin = "vision"
        → post.extraction_quality = "vision_ok" | "vision_low"
"""
from __future__ import annotations

from pathlib import Path

from scripts.models import RawPost


def _merge_vision_text(post: RawPost, result: dict) -> None:
    """将 vision_extract 结果合并写回 post。"""
    raw_text = str(result.get("raw_text") or "").strip()
    questions: list[str] = [str(q) for q in (result.get("questions") or []) if str(q).strip()]
    company = str(result.get("company") or "").strip()
    conf = float(result.get("extraction_confidence") or 0.0)

    # 拼合成正文
    parts: list[str] = []
    if raw_text:
        parts.append(raw_text)
    if questions:
        parts.append("\n【提取题目】\n" + "\n".join(f"- {q}" for q in questions))

    if parts:
        vision_body = "\n\n".join(parts)
        # 追加到现有正文后（不覆盖，保留原始 OCR 残片）
        existing = (post.raw_text or "").strip()
        post.raw_text = f"{existing}\n\n【Vision补读】\n{vision_body}".strip() if existing else vision_body

    if company and not post.company:
        post.company = company

    post.modality_origin = "vision"
    post.extraction_quality = "vision_ok" if conf >= 0.6 else "vision_low"
    post.needs_vision_fallback = False  # 已处理，清除标记


def run_vision_fallback(
    post: RawPost,
    *,
    asset_root: Path | None = None,
    extra_hint: str = "",
) -> bool:
    """对单条 post 执行 vision 补读，返回是否成功。"""
    from scripts.ai.gateway import vision_extract

    if not post.needs_vision_fallback and post.extraction_quality != "ocr_low_quality":
        return False

    paths: list[Path] = []
    for item in post.asset_paths or []:
        p = Path(str(item))
        if not p.is_absolute() and asset_root:
            p = asset_root / p
        if p.exists() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            paths.append(p)

    if not paths:
        return False

    improved = False
    for img_path in paths[:4]:  # 每帖最多处理 4 张图
        result = vision_extract(img_path, extra_hint=extra_hint)
        if result and (result.get("raw_text") or result.get("questions")):
            _merge_vision_text(post, result)
            improved = True

    return improved


def run_vision_fallback_batch(
    posts: list[RawPost],
    *,
    asset_root: Path | None = None,
    max_posts: int = 50,
) -> int:
    """批量补读需要 vision 的帖子，返回成功数量。"""
    candidates = [p for p in posts if p.needs_vision_fallback or p.extraction_quality == "ocr_low_quality"]
    candidates = candidates[:max_posts]

    success = 0
    for post in candidates:
        if run_vision_fallback(post, asset_root=asset_root):
            success += 1
    return success

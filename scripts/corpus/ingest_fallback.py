"""Role-aware ingest fallback — avoid silently loading the wrong job corpus."""
from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.config import cache_dir, list_ingest_fallback_candidates, sample_posts_path
from scripts.corpus.tech_roles import TECH_ROLES
from scripts.models import RawPost

_SPACE = re.compile(r"\s+")
_ROLE_NOISE = re.compile(
    r"(?:面经|面试|实习|校招|社招|秋招|春招|经验|分享|记录|汇总|整理|攻略)+",
    re.IGNORECASE,
)


def _norm(text: str) -> str:
    return _SPACE.sub("", (text or "").strip().lower())


def nonempty_posts(posts: list[RawPost]) -> list[RawPost]:
    return [p for p in posts if (p.raw_text or p.content_text or p.locator_text or "").strip()]


def ingest_attempted_live(config) -> bool:
    """User asked for network scrape (牛客 / 小红书 live), not local JSON import."""
    return bool(
        config.discover_nowcoder
        or config.nowcoder_urls
        or config.xhs_live
    )


def _target_role_aliases(role: str) -> set[str]:
    aliases: set[str] = set()
    role_norm = _norm(role)
    if role_norm:
        aliases.add(role_norm)

    matched_preset = False
    for preset in TECH_ROLES:
        preset_norms = {_norm(preset.search_as), _norm(preset.label)}
        if role_norm in preset_norms or any(role_norm in pn or pn in role_norm for pn in preset_norms):
            matched_preset = True
            aliases.update(preset_norms)
            for kw in preset.keywords:
                aliases.add(_norm(kw))

    if not matched_preset and role_norm:
        # Short tokens like "后端" from "后端开发"
        if len(role_norm) >= 4:
            aliases.add(role_norm[:2])
    return {a for a in aliases if len(a) >= 2}


def _hints_from_report(data: dict) -> list[str]:
    hints: list[str] = []
    for q in data.get("queries") or []:
        hints.append(str(q))
    desc = data.get("description")
    if desc:
        hints.append(str(desc))
    for post in data.get("posts") or []:
        if isinstance(post, dict):
            if post.get("role"):
                hints.append(str(post["role"]))
            text = (post.get("raw_text") or post.get("content_text") or "")[:120]
            if text:
                hints.append(text)
    return hints


def _hints_from_posts(posts: list[RawPost]) -> list[str]:
    hints: list[str] = []
    for post in posts:
        if post.role:
            hints.append(post.role)
        title = (post.raw_text or post.content_text or "")[:120]
        if title:
            hints.append(title)
    return hints


def corpus_matches_role(role: str, hints: list[str]) -> bool:
    """Heuristic: does this corpus look intended for the target role?"""
    if not hints:
        return False
    aliases = _target_role_aliases(role)
    if not aliases:
        return False

    for raw in hints:
        hint = _ROLE_NOISE.sub("", raw)
        hint_norm = _norm(hint)
        if not hint_norm:
            continue
        for alias in aliases:
            if alias in hint_norm or hint_norm in alias:
                return True
    return False


def load_report_hints(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        return _hints_from_posts([RawPost.from_dict(d) for d in data])
    if isinstance(data, dict):
        return _hints_from_report(data)
    return []


def corpus_path_matches_role(role: str, path: Path) -> bool:
    if path == sample_posts_path():
        # Bundled demo is always AI 应用开发 oriented.
        return corpus_matches_role(role, load_report_hints(path))
    return corpus_matches_role(role, load_report_hints(path))


def resolve_role_aware_fallback(role: str) -> Path | None:
    """Pick a local fallback file only when its content matches the target role."""
    for candidate in list_ingest_fallback_candidates():
        if corpus_path_matches_role(role, candidate):
            return candidate
    return None


def build_ingest_failure_message(role: str, config, queries: list[str]) -> str:
    parts = [
        f"未抓到任何面经帖（目标岗位：{role}）。",
    ]
    if ingest_attempted_live(config):
        parts.append(
            "已尝试联网抓取但无有效正文（牛客可能 WAF / 发现 0 URL / 小红书未配置）。"
            "不会自动改用其他岗位的本地语料。"
        )
    else:
        parts.append("未提供可用的本地语料，且未开启联网抓取。")

    parts.append(
        "建议：① 安全抓取小红书: uv run python -m scripts.tools.xhs_scrape_safe --role-id ai_app；"
        "② Web UI ⚙「安全抓取小红书」后勾选「导入本地 JSON」构建面经库；"
        "③ 牛客补充：勾选「联网发现牛客」或 --discover-nowcoder --refresh；"
        "④ --nowcoder-urls <牛客帖链接>；"
        "⑤ --raw-posts 指向与岗位匹配的 JSON。"
    )
    if queries:
        parts.append(f"检索词示例：{queries[0]}")
    local = list_ingest_fallback_candidates()
    if local:
        names = ", ".join(p.name for p in local)
        parts.append(f"本地已有语料（需岗位匹配才会自动使用）：{names}")
    return " ".join(parts)


def role_mismatch_warning(role: str, path: Path) -> str | None:
    if corpus_path_matches_role(role, path):
        return None
    return (
        f"语料文件 {path.name} 与目标岗位「{role}」不匹配；"
        "结果仍以目标岗位标签入库，请确认路径或换用匹配语料。"
    )


def is_demo_corpus_path(path: Path) -> bool:
    try:
        return path.resolve() == sample_posts_path().resolve()
    except OSError:
        return path.name == sample_posts_path().name

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from scripts.connectors.base import Connector, SearchResult
from scripts.models import RawPost


def _epoch_ms_to_iso(ms) -> str | None:
    if not ms:
        return None
    try:
        dt = datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None
    return dt.date().isoformat()


def parse_mediacrawler_export(json_text: str) -> list[RawPost]:
    notes = json.loads(json_text)
    posts: list[RawPost] = []
    for note in notes:
        title = (note.get("title") or "").strip()
        desc = (note.get("desc") or "").strip()
        raw_text = "\n".join(part for part in (title, desc) if part)
        posts.append(
            RawPost(
                source="xiaohongshu",
                url=note.get("note_url", ""),
                post_type="image",
                raw_text=raw_text,
                posted_at=_epoch_ms_to_iso(note.get("time")),
                asset_paths=list(note.get("image_list") or []),
            )
        )
    return posts


def _default_loader(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


class XiaohongshuConnector(Connector):
    name = "xiaohongshu"

    def __init__(self, export_path: str, loader: Callable[[str], str] | None = None):
        self.export_path = export_path
        self.loader = loader or _default_loader

    def search(self, queries: list[str]) -> SearchResult:
        try:
            posts = parse_mediacrawler_export(self.loader(self.export_path))
        except Exception as exc:  # noqa: BLE001 - degrade, never crash the pipeline
            return SearchResult.degraded(
                self.name,
                f"无法读取 MediaCrawler 导出 ({exc});请先用 MediaCrawler 登录并采集小红书笔记，导出 JSON 后再试",
            )
        return SearchResult(posts=posts, status="ok", message=f"{len(posts)} posts")

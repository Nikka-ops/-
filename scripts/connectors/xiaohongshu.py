import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from scripts.connectors.base import Connector, SearchResult
from scripts.models import RawPost
from scripts.scrape.mediacrawler_driver import MediaCrawlerDriver
from scripts.scrape.normalize_xhs import normalize


def _epoch_ms_to_iso(ms) -> str | None:
    if not ms:
        return None
    try:
        dt = datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None
    return dt.date().isoformat()


def _posts_from_notes(notes: list[dict]) -> list[RawPost]:
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


def parse_mediacrawler_export(json_text: str) -> list[RawPost]:
    return _posts_from_notes(json.loads(json_text))


def _default_loader(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


class XiaohongshuConnector(Connector):
    name = "xiaohongshu"

    def __init__(
        self,
        export_path: str | None = None,
        driver: MediaCrawlerDriver | None = None,
        loader: Callable[[str], str] | None = None,
    ):
        if export_path is None and driver is None:
            raise ValueError(
                "XiaohongshuConnector requires either export_path (pre-scraped JSON) "
                "or driver (MediaCrawlerDriver for on-demand scraping)"
            )
        self.export_path = export_path
        self.driver = driver
        self.loader = loader or _default_loader

    def search(self, queries: list[str]) -> SearchResult:
        try:
            if self.driver is not None:
                if not queries:
                    return SearchResult.degraded(
                        self.name,
                        "需要关键词才能用 MediaCrawler 驱动模式;请传入 queries",
                    )
                notes_path = self.driver.scrape_xhs(queries)
                native = json.loads(Path(notes_path).read_text(encoding="utf-8"))
                posts = _posts_from_notes(normalize(native))
            else:
                posts = parse_mediacrawler_export(self.loader(self.export_path))
        except Exception as exc:  # noqa: BLE001 - degrade, never crash the pipeline
            return SearchResult.degraded(
                self.name,
                f"无法获取小红书数据 ({exc});若用 driver 模式请检查 MediaCrawler 登录态是否过期(重扫码),"
                "或确认 MediaCrawler 是否安装在 $MEDIACRAWLER_HOME / ~/.mediacrawler/",
            )
        return SearchResult(posts=posts, status="ok", message=f"{len(posts)} posts")

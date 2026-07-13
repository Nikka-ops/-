import json
from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path

from scripts.connectors.base import Connector, SearchResult
from scripts.corpus.classify import extract_company_role
from scripts.config import full_scrape_recency_days
from scripts.models import RawPost
from scripts.ocr.xhs_images import build_locator_text, process_xhs_note_images
from scripts.scrape.spider_xhs_driver import SpiderXHSDriver
from scripts.scrape.normalize_xhs import normalize


def _epoch_ms_to_iso(ms) -> str | None:
    if not ms:
        return None
    try:
        dt = datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None
    return dt.date().isoformat()


def _within_recency(iso: str | None, window_days: int) -> bool:
    if not iso:
        return True
    try:
        posted = date.fromisoformat(iso[:10])
        return (date.today() - posted).days <= window_days
    except ValueError:
        return True


def _posts_from_notes(notes: list[dict], *, window_days: int | None = None) -> list[RawPost]:
    """Build RawPosts from normalized notes. ``window_days=None`` skips date filter (pipeline applies recency later)."""
    window = full_scrape_recency_days() if window_days is None else window_days
    posts: list[RawPost] = []
    for note in notes:
        posted_at = _epoch_ms_to_iso(note.get("time"))
        if window > 0 and not _within_recency(posted_at, window):
            continue
        title = (note.get("title") or "").strip()
        desc = (note.get("desc") or "").strip()
        tags = _coerce_tags(note.get("tags") or note.get("tag_list"))
        raw_text = build_locator_text(title, desc, tags)
        company, role = extract_company_role(title=title, tags=tags, desc=desc)
        posts.append(
            RawPost(
                source="xiaohongshu",
                url=note.get("note_url", ""),
                post_type="image",
                raw_text=raw_text,
                posted_at=_epoch_ms_to_iso(note.get("time")),
                asset_paths=list(note.get("image_list") or []),
                locator_text=raw_text,
                content_text=raw_text,
                extraction_quality="text_only",
                company=company,
                role=role,
            )
        )
    return posts


def posts_from_notes(notes: list[dict], *, window_days: int | None = None) -> list[RawPost]:
    """Public wrapper for export / ingest metrics."""
    return _posts_from_notes(notes, window_days=window_days)


def parse_mediacrawler_export(json_text: str) -> list[RawPost]:
    # No date filter here: the pipeline applies recency later, and callers
    # expect every note in the export to be parsed.
    return _posts_from_notes(json.loads(json_text), window_days=0)


def _coerce_tags(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        tags = []
        for item in value:
            if isinstance(item, dict):
                item = item.get("name") or item.get("tag_name") or item.get("text")
            text = str(item).strip()
            if text:
                tags.append(text)
        return tags
    if isinstance(value, str):
        normalized = value.replace("#", ",").replace("，", ",")
        return [part.strip() for part in normalized.split(",") if part.strip()]
    return []


def _note_id_from(note: dict) -> str:
    note_id = str(note.get("note_id") or "").strip()
    if note_id:
        return note_id
    note_url = str(note.get("note_url") or "").rstrip("/")
    return note_url.rsplit("/", 1)[-1] if note_url else "unknown"


def _default_loader(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


class XiaohongshuConnector(Connector):
    name = "xiaohongshu"

    def __init__(
        self,
        export_path: str | None = None,
        driver: SpiderXHSDriver | None = None,
        loader: Callable[[str], str] | None = None,
        login_type: str = "qrcode",
        asset_root="corpus_cache/assets/xhs",
        ocr_root="corpus_cache/ocr/xhs",
        http_get=None,
        ocr_engine=None,
        enable_image_ocr: bool = True,
    ):
        if export_path is None and driver is None:
            raise ValueError(
                "XiaohongshuConnector requires either export_path (pre-scraped JSON) "
                "or driver (SpiderXHSDriver for on-demand scraping)"
            )
        self.export_path = export_path
        self.driver = driver
        self.loader = loader or _default_loader
        self.login_type = login_type
        self.asset_root = asset_root
        self.ocr_root = ocr_root
        self.http_get = http_get
        self.ocr_engine = ocr_engine
        self.enable_image_ocr = enable_image_ocr

    def _posts_with_images(self, notes: list[dict]) -> list[RawPost]:
        posts: list[RawPost] = []
        for note in notes:
            title = (note.get("title") or "").strip()
            desc = (note.get("desc") or "").strip()
            image_urls = list(note.get("image_list") or [])
            posts.append(
                process_xhs_note_images(
                    note_id=_note_id_from(note),
                    note_url=note.get("note_url", ""),
                    title=title,
                    desc=desc,
                    tags=_coerce_tags(note.get("tags") or note.get("tag_list")),
                    image_urls=image_urls,
                    posted_at=_epoch_ms_to_iso(note.get("time")),
                    asset_root=self.asset_root,
                    ocr_root=self.ocr_root,
                    http_get=self.http_get,
                    ocr_engine=self.ocr_engine,
                    enable_ocr=self.enable_image_ocr,
                )
            )
        return posts

    def search(self, queries: list[str]) -> SearchResult:
        try:
            if self.driver is not None:
                if not queries:
                    return SearchResult.degraded(
                        self.name,
                        "需要关键词才能用 Spider_XHS 驱动模式;请传入 queries",
                    )
                notes_path = self.driver.scrape_xhs(queries)
                native = json.loads(Path(notes_path).read_text(encoding="utf-8"))
                posts = self._posts_with_images(normalize(native))
            else:
                notes = json.loads(self.loader(self.export_path))
                posts = self._posts_with_images(notes)
        except Exception as exc:  # noqa: BLE001 - degrade, never crash the pipeline
            return SearchResult.degraded(
                self.name,
                f"无法获取小红书数据 ({exc});若用 driver 模式请检查 CDP Chrome 是否已登录，"
                "或设置 XHS_COOKIES；确认 Spider_XHS 已安装在 $SPIDER_XHS_HOME / ~/.spider_xhs",
            )
        return SearchResult(posts=posts, status="ok", message=f"{len(posts)} posts")

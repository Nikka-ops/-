"""HTTP session helpers (shared by corpus + jobs; no circular imports)."""
from __future__ import annotations

import requests

_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def build_session(
    *,
    user_agent: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent or _DEFAULT_UA})
    if extra_headers:
        session.headers.update(extra_headers)
    return session

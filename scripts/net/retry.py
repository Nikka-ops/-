"""Shared retry helpers for scraping HTTP calls."""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

import requests

T = TypeVar("T")

_RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})


def is_retryable_http_error(exc: BaseException) -> bool:
    if isinstance(exc, requests.Timeout):
        return True
    if isinstance(exc, requests.ConnectionError):
        return True
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.status_code in _RETRYABLE_STATUS
    return False


def retry_call(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    backoff: tuple[float, ...] = (1.0, 2.0, 4.0),
    retry_on: Callable[[BaseException], bool] | None = None,
) -> T:
    """Run `fn` with retries on transient failures."""
    judge = retry_on or is_retryable_http_error
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            return fn()
        except BaseException as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= attempts - 1 or not judge(exc):
                raise
            delay = backoff[min(attempt, len(backoff) - 1)]
            if delay > 0:
                time.sleep(delay)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("retry_call failed without exception")


def request_with_retry(
    session: requests.Session,
    method: str,
    url: str,
    *,
    attempts: int = 3,
    backoff: tuple[float, ...] = (1.0, 2.0, 4.0),
    **kwargs,
) -> requests.Response:
    def _once() -> requests.Response:
        resp = session.request(method, url, **kwargs)
        if resp.status_code in _RETRYABLE_STATUS:
            resp.raise_for_status()
        return resp

    return retry_call(_once, attempts=attempts, backoff=backoff)

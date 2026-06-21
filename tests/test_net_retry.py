import pytest
import requests

from scripts.net.retry import is_retryable_http_error, retry_call


def test_is_retryable_timeout():
    assert is_retryable_http_error(requests.Timeout())


def test_retry_call_succeeds_after_failure():
    calls = 0

    def flaky():
        nonlocal calls
        calls += 1
        if calls < 2:
            raise requests.Timeout()
        return "ok"

    assert retry_call(flaky, attempts=3, backoff=(0.0, 0.0)) == "ok"
    assert calls == 2


def test_retry_call_raises_non_retryable():
    with pytest.raises(ValueError):
        retry_call(lambda: (_ for _ in ()).throw(ValueError("bad")), attempts=3, backoff=(0.0, 0.0))

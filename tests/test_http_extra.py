"""HTTP 层剩余分支测试"""
import http_client


def test_force_ipv4_is_safe():
    http_client.force_ipv4()
    assert True


def test_safe_error_redacts_env(clean_env):
    clean_env.setenv("SERVER_CHAN_KEY", "secret-key")
    clean_env.setenv("FETCH_PROXY", "http://user:pass@proxy")
    message = http_client._safe_error(RuntimeError("secret-key http://user:pass@proxy"))
    assert "secret-key" not in message
    assert "user:pass" not in message


def test_http_get_delegates(monkeypatch):
    calls = []
    monkeypatch.setattr(http_client, "_request_retry",
                        lambda *args, **kwargs: calls.append((args, kwargs)) or "response")
    assert http_client.http_get("https://x", timeout=7, encoding="gbk",
                                headers={"A": "B"}, reader_fallback=False) == "response"
    assert calls[0][0][0] == "GET"
    assert calls[0][1]["encoding"] == "gbk"
    assert calls[0][1]["reader_fallback"] is False


def test_http_post_delegates(monkeypatch):
    calls = []
    monkeypatch.setattr(http_client, "_request_retry",
                        lambda *args, **kwargs: calls.append((args, kwargs)) or "response")
    assert http_client.http_post("https://x", data={"a": 1}, timeout=9) == "response"
    assert calls[0][0][0] == "POST"
    assert calls[0][1]["reader_fallback"] is False
    assert calls[0][1]["data"] == {"a": 1}


def test_reset_session(monkeypatch):
    http_client._session = object()
    http_client.reset_session()
    assert http_client._session is None


def test_retry_after():
    class Response:
        def __init__(self, value):
            self.headers = {"Retry-After": value} if value is not None else {}

    assert http_client._retry_after(None) is None
    assert http_client._retry_after(Response("5")) == 5
    assert http_client._retry_after(Response("abc")) is None
    assert http_client._retry_after(Response("999")) == http_client.MAX_RETRY_AFTER
    assert http_client._retry_after(Response("-3")) == 0


def test_new_session_without_ua(clean_env):
    session = http_client._new_session(ua=False)
    assert session.headers.get("User-Agent") not in http_client.USER_AGENTS

"""HTTP 重试、Reader 兜底与下载限制测试"""
import pytest
import requests

import http_client


def test_reader_proxy_empty_env_uses_default(clean_env):
    assert http_client.reader_proxy() == http_client.DEFAULT_READER_PROXY
    clean_env.setenv("READER_PROXY", "")
    assert http_client.reader_proxy() == http_client.DEFAULT_READER_PROXY
    clean_env.setenv("READER_PROXY", "https://reader.example/{url}")
    assert http_client.reader_proxy() == "https://reader.example/{url}"


def test_reader_url_template_and_prefix():
    assert http_client._reader_url("https://a.com/x", "https://r/{url}") == "https://r/https://a.com/x"
    assert http_client._reader_url("https://a.com/x", "https://r/") == "https://r/https://a.com/x"
    assert http_client._reader_url("https://a.com/x", "") == ""


def test_browser_headers_no_brotli_and_referer():
    headers = http_client.browser_headers("https://example.com")
    assert headers["User-Agent"] in http_client.USER_AGENTS
    assert headers["Referer"] == "https://example.com"
    assert "Accept-Encoding" not in headers


def test_new_session_ignores_env_and_uses_explicit_proxy(clean_env):
    clean_env.setenv("FETCH_PROXY", "http://proxy:8080")
    session = http_client._new_session()
    assert session.trust_env is False
    assert session.proxies["http"] == "http://proxy:8080"
    assert session.proxies["https"] == "http://proxy:8080"


def test_fetch_once_antibot_and_errors(fake_session, fake_response):
    ok = http_client._fetch_once(fake_session(fake_response(200)), "GET", "https://x", 5)
    assert ok.status_code == 200
    for status in (403, 412):
        with pytest.raises(requests.HTTPError) as info:
            http_client._fetch_once(fake_session(fake_response(status)), "GET", "https://x", 5)
        assert info.value.response.status_code == status
    with pytest.raises(requests.HTTPError):
        http_client._fetch_once(fake_session(fake_response(404)), "GET", "https://x", 5)


def _patch_session(monkeypatch, session):
    monkeypatch.setattr(http_client, "get_session", lambda: session)


def test_request_retry_success_sets_encoding(monkeypatch, fake_session, fake_response):
    session = fake_session(fake_response(200, text="中文"))
    _patch_session(monkeypatch, session)
    response = http_client._request_retry("GET", "https://x", 5, encoding="gbk")
    assert response.text == "中文"
    assert response.encoding == "gbk"
    assert len(session.calls) == 1


def test_request_retry_antibot_uses_reader(monkeypatch, fake_session, fake_response):
    session = fake_session(fake_response(403))
    _patch_session(monkeypatch, session)
    reader = fake_response(200, text="x" * 400)
    reader.is_markdown = True
    monkeypatch.setattr(http_client, "_reader_fetch", lambda url, timeout: reader)
    assert http_client._request_retry("GET", "https://x", 5) is reader
    assert len(session.calls) == 1


def test_request_retry_404_does_not_retry_or_reader(monkeypatch, fake_session, fake_response):
    session = fake_session(fake_response(404))
    _patch_session(monkeypatch, session)
    called = []
    monkeypatch.setattr(http_client, "_reader_fetch", lambda *a: called.append(1))
    with pytest.raises(requests.HTTPError):
        http_client._request_retry("GET", "https://x", 5)
    assert len(session.calls) == 1
    assert called == []


def test_request_retry_500_retries_then_reader_fallback(monkeypatch, fake_session, fake_response):
    session = fake_session(fake_response(500), fake_response(500), fake_response(500))
    _patch_session(monkeypatch, session)
    reader = fake_response(200, text="x" * 400)
    monkeypatch.setattr(http_client, "_reader_fetch", lambda *a: reader)
    assert http_client._request_retry("GET", "https://x", 5) is reader
    assert len(session.calls) == 3


def test_request_retry_429_honors_retry_after(monkeypatch, fake_session, fake_response):
    session = fake_session(fake_response(429, headers={"Retry-After": "0"}),
                           fake_response(200, text="ok"))
    _patch_session(monkeypatch, session)
    response = http_client._request_retry("GET", "https://x", 5)
    assert response.text == "ok"
    assert len(session.calls) == 2


def test_request_retry_connection_error_retries(monkeypatch, fake_session, fake_response):
    session = fake_session(requests.ConnectionError("boom"), fake_response(200, text="ok"))
    _patch_session(monkeypatch, session)
    assert http_client._request_retry("GET", "https://x", 5).text == "ok"


def test_reader_fetch_marks_markdown_without_site_encoding(monkeypatch, fake_response):
    response = fake_response(200, text="中" * 301)

    class FakeNewSession:
        def get(self, url, timeout):
            return response

    monkeypatch.setattr(http_client, "_new_session", lambda ua=True: FakeNewSession())
    result = http_client._reader_fetch("https://example.com/a", 5)
    assert result is response
    assert result.is_markdown is True
    assert result.encoding is None


def test_reader_fetch_failures(monkeypatch, fake_response):
    class FakeNewSession:
        def __init__(self, response):
            self.response = response

        def get(self, url, timeout):
            if isinstance(self.response, Exception):
                raise self.response
            return self.response

    monkeypatch.setattr(http_client, "_new_session",
                        lambda ua=True: FakeNewSession(fake_response(500)))
    assert http_client._reader_fetch("https://x", 5) is None
    monkeypatch.setattr(http_client, "_new_session",
                        lambda ua=True: FakeNewSession(RuntimeError("boom")))
    assert http_client._reader_fetch("https://x", 5) is None


def test_reader_fetch_disabled(monkeypatch):
    monkeypatch.setattr(http_client, "reader_proxy", lambda: "")
    assert http_client._reader_fetch("https://x", 1) is None


def test_http_download_limits_size(monkeypatch, fake_response):
    monkeypatch.setattr(http_client, "_request_retry",
                        lambda *a, **k: fake_response(content=b"x" * 10))
    assert http_client.http_download("https://x", max_bytes=10) == b"x" * 10
    with pytest.raises(ValueError):
        http_client.http_download("https://x", max_bytes=9)

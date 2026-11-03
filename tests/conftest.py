"""共享测试夹具：禁止真实网络，固定时间与随机延时"""
import datetime

import pytest
import requests


class FakeResponse:
    def __init__(self, status_code=200, text="", content=b"", headers=None,
                 json_data=None, json_error=False):
        self.status_code = status_code
        self.text = text
        self.content = content
        self.headers = headers or {}
        self.encoding = None
        self.is_markdown = False
        self._json_data = json_data
        self._json_error = json_error

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        if self._json_error:
            raise ValueError("not json")
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)


class FakeSession:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []
        self.headers = {}
        self.proxies = {}

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if not self.results:
            raise AssertionError(f"unexpected request: {method} {url}")
        item = self.results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)


@pytest.fixture
def today():
    return datetime.date(2026, 11, 3)


@pytest.fixture
def make_job():
    from models import Job

    def _make(**overrides):
        values = {
            "title": "天水市第一人民医院临床医学招聘公告",
            "unit": "天水市第一人民医院",
            "link": "https://example.com/jobs/1",
            "source": "事业单位招聘网",
            "publish_date": "2026-10-20",
            "deadline": "2026-11-10",
        }
        values.update(overrides)
        return Job(**values)

    return _make


@pytest.fixture
def fake_response():
    return FakeResponse


@pytest.fixture
def fake_session():
    return FakeSession


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("network disabled in tests")

    monkeypatch.setattr(requests.Session, "request", boom)
    monkeypatch.setattr(requests, "post", boom)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    import http_client
    import parsers

    monkeypatch.setattr(http_client.time, "sleep", lambda *_: None)
    monkeypatch.setattr(parsers, "polite_delay", lambda: None)


@pytest.fixture
def clean_env(monkeypatch):
    import os

    for key in list(os.environ):
        if key.startswith("SERVER_CHAN_KEY") or key in {
            "PAGES_URL", "GITHUB_REPOSITORY", "FETCH_PROXY", "READER_PROXY", "TIMEZONE",
        }:
            monkeypatch.delenv(key, raising=False)
    return monkeypatch

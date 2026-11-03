"""各数据源抓取函数测试（全部离线）"""
import sys
import types

import parsers


def _anchor(title, href):
    return f'<a href="{href}">{title}</a>'


def test_fetch_guokao_filters_titles(monkeypatch, fake_response):
    html = "".join([
        _anchor("2026年度考试录用公务员公告", "/gk.html"),
        _anchor("某单位普通招聘公告", "/other.html"),
    ])
    monkeypatch.setattr(parsers, "http_get", lambda *a, **k: fake_response(text=html))
    jobs = parsers._fetch_guokao()
    assert len(jobs) == 1
    assert jobs[0].source == "国家公务员局"
    assert jobs[0].link == "http://www.scs.gov.cn/gk.html"


def test_fetch_gszg_dedupes_across_urls(monkeypatch, fake_response):
    first = _anchor("甘肃省公务员招录公告", "/a.html")
    second = _anchor("甘肃省公务员招录公告", "/a.html") + _anchor("甘肃省选调生公告", "/b.html")

    def fake_get(url, **kwargs):
        return fake_response(text=first if url.endswith("gszg.gov.cn") else second)

    monkeypatch.setattr(parsers, "http_get", fake_get)
    jobs = parsers._fetch_gszg()
    assert len(jobs) == 2
    assert {j.link for j in jobs} == {
        "http://www.gszg.gov.cn/a.html", "http://www.gszg.gov.cn/b.html",
    }


def test_fetch_gansu_hr_falls_back_to_second_url(monkeypatch, fake_response):
    html = _anchor("甘肃省事业单位招聘公告", "/hr.html")
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            raise RuntimeError("waf")
        return fake_response(text=html)

    monkeypatch.setattr(parsers, "http_get", fake_get)
    jobs = parsers._fetch_gansu_hr()
    assert len(jobs) == 1
    assert jobs[0].source == "甘肃省人社厅"
    assert len(calls) == 2


def test_fetch_shaanxi(monkeypatch, fake_response):
    html = _anchor("陕西省事业单位招聘公告", "/sx.html")
    monkeypatch.setattr(parsers, "http_get", lambda *a, **k: fake_response(text=html))
    jobs = parsers._fetch_shaanxi()
    assert len(jobs) == 1
    assert jobs[0].link == "http://rst.shaanxi.gov.cn/sx.html"


def test_fetch_xapta_direct_and_playwright_fallback(monkeypatch, fake_response):
    long_html = "x" * 2001 + _anchor("西安市事业单位招聘公告", "/xa.html")
    monkeypatch.setattr(parsers, "http_get", lambda *a, **k: fake_response(text=long_html))
    jobs = parsers._fetch_xapta()
    assert len(jobs) == 1

    monkeypatch.setattr(parsers, "http_get", lambda *a, **k: fake_response(text="short"))
    monkeypatch.setattr(parsers, "_xapta_playwright", lambda url: ["fallback"])
    assert parsers._fetch_xapta() == ["fallback"]


def test_fetch_xapta_http_error_falls_back(monkeypatch):
    monkeypatch.setattr(parsers, "http_get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("tls")))
    monkeypatch.setattr(parsers, "_xapta_playwright", lambda url: ["fallback"])
    assert parsers._fetch_xapta() == ["fallback"]


def test_xapta_playwright_without_dependency(monkeypatch):
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "playwright.sync_api":
            raise ImportError("no playwright")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    assert parsers._xapta_playwright("https://x") == []


def test_fetch_mohrss_falls_back_to_list(monkeypatch, fake_response):
    html = _anchor("某事业单位招聘公告", "/list.html")
    monkeypatch.setattr(parsers, "http_post", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("json down")))
    monkeypatch.setattr(parsers, "http_get", lambda *a, **k: fake_response(text=html))
    jobs = parsers._fetch_mohrss()
    assert len(jobs) == 1
    assert jobs[0].source == "中国公共招聘网"


def test_fetch_shiyebian_markdown_branch(monkeypatch, fake_response):
    md = "[2026年天水市事业单位招聘公告](https://www.shiyebian.net/a.html)"
    response = fake_response(text=md)
    response.is_markdown = True
    monkeypatch.setattr(parsers, "http_get", lambda *a, **k: response)
    jobs = parsers._fetch_shiyebian(today=__import__("datetime").date(2026, 11, 3))
    assert jobs
    assert jobs[0].title == "2026年天水市事业单位招聘公告"


def test_fetch_shiyebian_failures(monkeypatch):
    import pytest
    monkeypatch.setattr(parsers, "http_get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    with pytest.raises(RuntimeError):
        parsers._fetch_shiyebian()


def test_fetch_gaoxiaojob_warmup_failure(monkeypatch, fake_response):
    class BrokenSession:
        def get(self, *args, **kwargs):
            raise RuntimeError("cookie fail")

    monkeypatch.setattr(parsers, "get_session", lambda: BrokenSession())
    monkeypatch.setattr(parsers, "http_get", lambda *a, **k: fake_response(text=""))
    assert parsers._fetch_gaoxiaojob() == []


def test_fetch_gaoxiaojob_filters_non_detail_links(monkeypatch, fake_response):
    html = _anchor("某某大学招聘公告", "/news/1.html")

    class Session:
        def get(self, *args, **kwargs):
            return None

    monkeypatch.setattr(parsers, "get_session", lambda: Session())
    monkeypatch.setattr(parsers, "http_get", lambda *a, **k: fake_response(text=html))
    assert parsers._fetch_gaoxiaojob() == []


def test_to_job_maps_fields():
    job = parsers._to_job({"title": "招聘公告", "link": "https://x"}, "来源")
    assert job.source == "来源"
    assert job.unit == "来源"
    assert job.title == "招聘公告"


def test_xapta_playwright_success(monkeypatch):
    class FakePage:
        def goto(self, *a, **k):
            pass

        def wait_for_timeout(self, *a, **k):
            pass

        def content(self):
            return _anchor("西安市事业单位招聘公告", "/xa.html")

    class FakeBrowser:
        def new_page(self, **kwargs):
            return FakePage()

        def close(self):
            pass

    class FakeChromium:
        def launch(self, **kwargs):
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

    class FakeManager:
        def __enter__(self):
            return FakePlaywright()

        def __exit__(self, *args):
            return False

    fake_module = types.SimpleNamespace(sync_playwright=lambda: FakeManager())
    monkeypatch.setitem(sys.modules, "playwright", types.SimpleNamespace(sync_api=fake_module))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_module)
    jobs = parsers._xapta_playwright("https://xapta.xa.gov.cn")
    assert len(jobs) == 1
    assert jobs[0].source == "西安人事考试网"


def test_fetch_shaanxi_failure_raises(monkeypatch):
    import pytest
    monkeypatch.setattr(parsers, "http_get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    with pytest.raises(RuntimeError):
        parsers._fetch_shaanxi()


def test_run_all_reports_real_source_failure(monkeypatch):
    monkeypatch.setattr(parsers, "force_ipv4", lambda: None)
    monkeypatch.setattr(parsers, "http_get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("blocked")))
    monkeypatch.setattr(parsers, "FETCHERS", [("bad", parsers._fetch_shaanxi)])
    jobs, report = parsers.run_all(return_report=True)
    assert jobs == []
    assert report[0]["count"] == 0
    assert "blocked" in report[0]["error"]

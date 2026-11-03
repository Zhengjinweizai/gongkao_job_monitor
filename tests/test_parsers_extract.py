"""列表解析、日期与数据源抓取测试"""
import datetime

import pytest

import parsers
from parsers import (
    _combine_md,
    _iter_mohrss_items,
    _province_from_path,
    extract_announcements,
    extract_announcements_md,
    extract_date,
    run_all,
)


def _anchor(title, href):
    return f'<a href="{href}">{title}</a>'


def test_extract_announcements_filters_and_urljoin():
    html = "<html><body>" + "".join([
        _anchor("某某单位招聘公告", "/a.html"),
        _anchor("拟录用人员公示名单", "/bad.html"),
        _anchor("某某单位招聘公告", "/a.html"),
        _anchor("某某单位招聘公告", "/style.css"),
        _anchor("某某单位招聘公告", "/x.js"),
        _anchor("某某单位招聘公告", "/x.jsp"),
        _anchor("某某单位招聘公告", "/x.json"),
        _anchor("某某单位招聘公告", "javascript:alert(1)"),
        _anchor("短公告", "/short.html"),
    ]) + "</body></html>"
    items = extract_announcements(html, "https://example.com/gs/index.html")
    links = [i["link"] for i in items]
    assert "https://example.com/a.html" in links
    assert "https://example.com/x.jsp" in links
    assert "https://example.com/x.json" in links
    assert not any("/bad" in link or link.endswith(".css") or link.endswith(".js") for link in links)
    assert links.count("https://example.com/a.html") == 1


def test_extract_announcements_title_length_bounds():
    html = "".join([
        _anchor("某单位招聘公告", "/7.html"),          # 7 字
        _anchor("某某单位招聘公告", "/8.html"),        # 8 字
        _anchor("招聘" * 60, "/120.html"),             # 120 字
        _anchor("招聘" * 60 + "甲", "/121.html"),      # 121 字
    ])
    links = [i["link"] for i in extract_announcements(html, "https://example.com/")]
    assert "https://example.com/8.html" in links
    assert "https://example.com/120.html" in links
    assert "https://example.com/7.html" not in links
    assert "https://example.com/121.html" not in links


def test_extract_announcements_markdown():
    md = "\n".join([
        "[某某单位招聘公告](https://example.com/a)",
        "[拟录用人员公示](https://example.com/bad)",
        "[短公告](https://example.com/short)",
        "[某某单位招聘公告](https://example.com/a)",
        "[某某单位招聘公告](javascript:alert(1))",
    ])
    items = extract_announcements_md(md, "https://example.com")
    assert items == [{"title": "某某单位招聘公告", "link": "https://example.com/a"}]


def test_extract_announcements_dispatch_markdown():
    md = "[某某单位招聘公告](https://example.com/a)"
    assert extract_announcements(md, "https://example.com") == [
        {"title": "某某单位招聘公告", "link": "https://example.com/a"}
    ]


def test_extract_announcements_empty():
    assert extract_announcements("", "https://example.com") == []
    assert extract_announcements(None, "https://example.com") == []
    assert extract_announcements_md("", "https://example.com") == []


@pytest.mark.parametrize("value, expected", [
    ("2026年11月3日", "2026-11-03"),
    ("2026-11-03", "2026-11-03"),
    ("2026/11/3", "2026-11-03"),
    ("2026.11.3", "2026-11-03"),
    ("报名时间 2026年11月3日", "2026-11-03"),
    ("2026年11月3号", "2026-11-03"),
    ("2026-02-30", ""),
    ("", ""),
    (None, ""),
])
def test_extract_date(value, expected):
    assert extract_date(value) == expected


def test_combine_md():
    today = datetime.date(2026, 11, 3)
    assert _combine_md("11-03", today) == "2026-11-03"
    assert _combine_md("12-30", today) == "2025-12-30"
    assert _combine_md("01-05", today, "2024年公告") == "2024-01-05"
    assert _combine_md("2026-05-22", today) == "2026-05-22"
    assert _combine_md("13-40", today) == ""
    assert _combine_md("no date", today) == ""


def test_province_from_path():
    assert _province_from_path("/gansu/") == "甘肃"
    assert _province_from_path("/shanxisheng/") == "陕西"
    assert _province_from_path("/shanxi/") == "山西"
    assert _province_from_path("/unknown/") == ""
    assert _province_from_path(None) == ""


def test_iter_mohrss_items():
    assert _iter_mohrss_items([{"a": 1}, "x"]) == [{"a": 1}]
    assert _iter_mohrss_items({"data": [{"b": 2}]}) == [{"b": 2}]
    assert _iter_mohrss_items({"data": {"list": [{"c": 3}]}}) == [{"c": 3}]
    assert _iter_mohrss_items({"data": "no"}) == []
    assert _iter_mohrss_items(None) == []


def test_run_all_isolates_failures_and_reports(monkeypatch):
    good = parsers.Job(title="岗位", link="https://example.com/1")
    monkeypatch.setattr(parsers, "force_ipv4", lambda: None)
    monkeypatch.setattr(parsers, "FETCHERS", [
        ("ok", lambda: [good]),
        ("boom", lambda: (_ for _ in ()).throw(RuntimeError("fail"))),
        ("none", lambda: None),
    ])
    jobs, report = run_all(return_report=True)
    assert jobs == [good]
    assert [r["count"] for r in report] == [1, 0, 0]
    assert "fail" in report[1]["error"]
    assert "returned None" in report[2]["error"]


def test_fetch_mohrss_json_payload(monkeypatch, fake_response):
    payload = {"data": [
        {"title": "某事业单位招聘", "contentId": "42", "renshu": "3"},
        {"title": "", "contentId": "x"},
        {"title": "缺 id"},
    ]}
    monkeypatch.setattr(parsers, "http_post", lambda *a, **k: fake_response(json_data=payload))
    jobs = parsers._fetch_mohrss()
    assert len(jobs) == 1
    assert jobs[0].title == "某事业单位招聘（3）"
    assert jobs[0].link.endswith("/sydwgg/42/.jhtml")


def test_fetch_shiyebian_parses_list(monkeypatch, fake_response):
    html = """
    <ul class="list-index">
      <li><em>11-03</em>
        <a href="/gansu/">天水</a>
        <a href="/gansu/1.html">2026年天水市事业单位招聘公告</a>
      </li>
      <li><em>10-01</em><a href="/gansu/">天水</a></li>
    </ul>"""
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return fake_response(text=html)

    monkeypatch.setattr(parsers, "http_get", fake_get)
    jobs = parsers._fetch_shiyebian(today=datetime.date(2026, 11, 3))
    assert jobs
    assert all(j.source == "事业单位招聘网" for j in jobs)
    assert jobs[0].province == "甘肃"
    assert jobs[0].city == "天水"
    assert jobs[0].publish_date == "2026-11-03"
    assert calls[0][1]["encoding"] == "gbk"


def test_fetch_gaoxiaojob_separates_category(monkeypatch, fake_response):
    html = ('<a href="/announcement/detail/1.html">医学人才：某某大学招聘公告</a>')
    monkeypatch.setattr(parsers, "get_session", lambda: type("S", (), {"get": lambda self, *a, **k: None})())

    def fake_get(url, **kwargs):
        return fake_response(text=html if "/column/5.html" in url else "")

    monkeypatch.setattr(parsers, "http_get", fake_get)
    jobs = parsers._fetch_gaoxiaojob()
    assert len(jobs) == 1
    assert jobs[0].category == "医学人才"
    assert jobs[0].unit == ""
    assert jobs[0].title == "某某大学招聘公告"

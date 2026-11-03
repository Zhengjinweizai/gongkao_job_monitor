"""主流程、历史迁移与清理测试"""
import datetime

import main
from models import Job


def test_resolve_pages_url(clean_env):
    assert main.resolve_pages_url() == ""
    clean_env.setenv("GITHUB_REPOSITORY", "u/r")
    assert main.resolve_pages_url() == "https://u.github.io/r/history.html"
    clean_env.setenv("GITHUB_REPOSITORY", "u/u.github.io")
    assert main.resolve_pages_url() == "https://u.github.io/history.html"
    clean_env.setenv("PAGES_URL", " https://example.com/h.html ")
    assert main.resolve_pages_url() == "https://example.com/h.html"
    clean_env.setenv("PAGES_URL", "https://github.com/u/r/deployments/github-pages")
    assert main.resolve_pages_url() == "https://u.github.io/history.html"
    clean_env.delenv("GITHUB_REPOSITORY")
    assert main.resolve_pages_url() == ""


def test_as_date():
    assert main._as_date("2026-11-03") == datetime.date(2026, 11, 3)
    assert main._as_date(datetime.date(2026, 11, 3)) == datetime.date(2026, 11, 3)
    assert main._as_date(datetime.datetime(2026, 11, 3, 12)) == datetime.date(2026, 11, 3)


def test_purge_expired_grace():
    history = {"jobs": [
        {"deadline": "2026-11-01", "unique_id": "remove-2"},
        {"deadline": "2026-11-02", "unique_id": "keep-1"},
        {"deadline": "2026-11-03", "unique_id": "keep-0"},
        {"deadline": "2026-11-07", "unique_id": "keep-active"},
        {"publish_date": "2026-10-03", "unique_id": "keep-inferred"},
        {"publish_date": "2026-10-02", "unique_id": "remove-inferred"},
        {"publish_date": "", "deadline": "", "first_seen": "2026-10-04", "unique_id": "keep-fallback"},
        {"publish_date": "", "deadline": "", "first_seen": "2026-10-02", "unique_id": "remove-fallback"},
    ]}
    result = main.purge_expired(history, datetime.date(2026, 11, 3))
    ids = {j["unique_id"] for j in result["jobs"]}
    assert ids == {"keep-1", "keep-0", "keep-active", "keep-inferred",
                   "keep-fallback"}
    kept_one = next(j for j in result["jobs"] if j["unique_id"] == "keep-1")
    assert kept_one["status"] == "expired"
    assert kept_one["days_left"] == -1


def test_prepare_history_migrates_and_dedupes():
    raw = {
        "title": "某某大学招聘公告",
        "unit": "医学人才",
        "source": "高校人才网",
        "link": "https://example.com/job/1?utm_source=a",
        "fetched_at": "2026-08-16",
        "score": 5,
        "tier": 2,
        "match_explanation": ["旧"],
    }
    duplicate = dict(raw, unit="兰州", fetched_at="2026-08-17", link="https://EXAMPLE.com/job/1/")
    history, = (main.prepare_history({"jobs": [raw, duplicate]}, "2026-11-03"),)
    assert len(history["jobs"]) == 1
    job = history["jobs"][0]
    assert job["unit"] == ""
    assert job["category"] in ("医学人才", "兰州")
    assert job["unique_id"] == Job(link=raw["link"]).unique_id()
    assert job["first_seen"] == "2026-08-16"
    # 标题没有专业词，unit 不再贡献 +5；地区也无法从“医学人才”推断
    assert job["score"] == 0
    assert job["status"] == "expired"


def test_prepare_history_merges_attachments_and_skips_bad_rows():
    a = {"title": "招聘", "link": "https://x/a", "attachments": ["https://x/a.pdf"],
         "fetched_at": "2026-10-01", "score": 5}
    b = {"title": "招聘", "link": "https://x/a/", "attachments": ["https://x/b.pdf"],
         "fetched_at": "2026-10-02", "deadline": "2026-11-10", "score": 3}
    history, = (main.prepare_history({"jobs": [a, b, "bad"]}, "2026-11-03"),)
    assert len(history["jobs"]) == 1
    assert history["jobs"][0]["deadline"] == "2026-11-10"
    assert set(history["jobs"][0]["attachments"]) == {"https://x/a.pdf", "https://x/b.pdf"}


def test_prepare_history_non_list_jobs():
    history, = (main.prepare_history({"jobs": None}, "2026-11-03"),)
    assert history["jobs"] == []


def _high_job(make_job, link="https://example.com/high"):
    return make_job(title="天水市第一人民医院临床医学招聘", unit="天水市第一人民医院",
                    link=link, deadline="2026-11-10", publish_date="2026-10-20",
                    source="事业单位招聘网")


def test_main_end_to_end(monkeypatch, make_job, today):
    high = _high_job(make_job)
    mid = make_job(title="甘肃某单位招聘公告", unit="", link="https://example.com/mid",
                   deadline="2026-11-10", publish_date="2026-10-20")
    low = make_job(title="某单位招聘公告", unit="", link="https://example.com/low",
                   deadline="2026-11-10", publish_date="2026-10-20")
    expired = make_job(title="天水市临床医学招聘", link="https://example.com/expired",
                       deadline="2026-10-01", publish_date="2026-09-01")
    duplicate = _high_job(make_job)

    saved = {}
    pushed = {}
    rendered = {}
    detail_links = []

    monkeypatch.setattr(main.storage, "load_history", lambda: {"jobs": []})
    monkeypatch.setattr(main.storage, "save_history", lambda data: saved.update(data))
    monkeypatch.setattr(main, "run_all", lambda return_report=False: (
        [high, mid, low, expired, duplicate],
        [{"name": "测试源", "count": 5, "error": ""}],
    ))
    monkeypatch.setattr(main, "fetch_detail", lambda job: detail_links.append(job.link) or True)
    monkeypatch.setattr(main, "parse_attachments", lambda job, max_count=2: 0)
    monkeypatch.setattr(main.generate_html, "render",
                        lambda history, today, pages_url=None: rendered.update(
                            {"history": history, "today": today, "pages_url": pages_url}))
    monkeypatch.setattr(main, "resolve_pages_url", lambda: "https://u.github.io/r/history.html")
    monkeypatch.setattr(main.notifier, "build_batch", lambda jobs, pages_url="": "BATCH")
    monkeypatch.setattr(main.notifier, "push",
                        lambda title, desp: pushed.update({"title": title, "desp": desp}) or True)

    summary = main.main(today=today)
    assert summary["new"] == 2
    assert summary["pushed"] == 1
    assert summary["history"] == 2
    assert set(detail_links) == {"https://example.com/high", "https://example.com/mid"}
    assert len(saved["jobs"]) == 2
    assert {j["link"] for j in saved["jobs"]} == {"https://example.com/high", "https://example.com/mid"}
    assert all(j["fetched_at"] == "2026-11-03" for j in saved["jobs"])
    assert len(rendered["history"]["jobs"]) == 2
    assert rendered["pages_url"] == "https://u.github.io/r/history.html"
    assert pushed["title"].startswith("📢")
    assert "1 个" in pushed["title"]


def test_main_detail_cap(monkeypatch, make_job, today):
    jobs = [
        _high_job(make_job, link="https://example.com/1"),
        _high_job(make_job, link="https://example.com/2"),
        _high_job(make_job, link="https://example.com/3"),
    ]
    calls = []
    monkeypatch.setattr(main.storage, "load_history", lambda: {"jobs": []})
    monkeypatch.setattr(main.storage, "save_history", lambda data: None)
    monkeypatch.setattr(main, "run_all", lambda return_report=False: (
        jobs, [{"name": "s", "count": 3, "error": ""}]))
    monkeypatch.setattr(main, "MAX_DETAIL_FETCH", 1)
    monkeypatch.setattr(main, "fetch_detail", lambda job: calls.append(job.link) or True)
    monkeypatch.setattr(main, "parse_attachments", lambda job, max_count=2: 0)
    monkeypatch.setattr(main.generate_html, "render", lambda *a, **k: None)
    monkeypatch.setattr(main, "resolve_pages_url", lambda: "")
    monkeypatch.setattr(main.notifier, "push", lambda *a: True)
    monkeypatch.setattr(main.notifier, "build_batch", lambda *a, **k: "B")
    main.main(today=today)
    assert calls == ["https://example.com/1"]


def test_main_all_sources_failed_alert(monkeypatch, today):
    pushed = {}
    monkeypatch.setattr(main.storage, "load_history", lambda: {"jobs": []})
    monkeypatch.setattr(main.storage, "save_history", lambda data: None)
    monkeypatch.setattr(main, "run_all", lambda return_report=False: (
        [], [{"name": "a", "count": 0, "error": "boom"},
             {"name": "b", "count": 0, "error": ""}]))
    monkeypatch.setattr(main.generate_html, "render", lambda *a, **k: None)
    monkeypatch.setattr(main, "resolve_pages_url", lambda: "")
    monkeypatch.setattr(main.notifier, "push",
                        lambda title, desp: pushed.update({"title": title, "desp": desp}) or True)
    main.main(today=today)
    assert "抓取异常" in pushed["title"]
    assert "boom" in pushed["desp"]


def test_main_skips_expired_new_jobs(monkeypatch, make_job, today):
    expired = make_job(title="天水市临床医学招聘", link="https://example.com/expired",
                       deadline="2026-10-01", publish_date="2026-09-01")
    saved = {}
    monkeypatch.setattr(main.storage, "load_history", lambda: {"jobs": []})
    monkeypatch.setattr(main.storage, "save_history", lambda data: saved.update(data))
    monkeypatch.setattr(main, "run_all", lambda return_report=False: (
        [expired], [{"name": "s", "count": 1, "error": ""}]))
    monkeypatch.setattr(main, "fetch_detail", lambda job: True)
    monkeypatch.setattr(main, "parse_attachments", lambda job, max_count=2: 0)
    monkeypatch.setattr(main.generate_html, "render", lambda *a, **k: None)
    monkeypatch.setattr(main, "resolve_pages_url", lambda: "")
    monkeypatch.setattr(main.notifier, "push", lambda *a: True)
    monkeypatch.setattr(main.notifier, "build_batch", lambda *a, **k: "B")
    summary = main.main(today=today)
    assert summary["new"] == 0
    assert saved["jobs"] == []


def test_main_known_job_not_readded(monkeypatch, make_job, today):
    known = _high_job(make_job, link="https://example.com/known")
    seed = known.to_dict()
    seed["fetched_at"] = "2026-10-01"
    saved = {}
    monkeypatch.setattr(main.storage, "load_history", lambda: {"jobs": [seed]})
    monkeypatch.setattr(main.storage, "save_history", lambda data: saved.update(data))
    monkeypatch.setattr(main, "run_all", lambda return_report=False: (
        [known], [{"name": "s", "count": 1, "error": ""}]))
    monkeypatch.setattr(main.generate_html, "render", lambda *a, **k: None)
    monkeypatch.setattr(main, "resolve_pages_url", lambda: "")
    monkeypatch.setattr(main.notifier, "push", lambda *a: True)
    summary = main.main(today=today)
    assert summary["new"] == 0
    assert len(saved["jobs"]) == 1


def test_main_detail_failure_still_saves(monkeypatch, make_job, today):
    job = _high_job(make_job)
    saved = {}
    monkeypatch.setattr(main.storage, "load_history", lambda: {"jobs": []})
    monkeypatch.setattr(main.storage, "save_history", lambda data: saved.update(data))
    monkeypatch.setattr(main, "run_all", lambda return_report=False: (
        [job], [{"name": "s", "count": 1, "error": ""}]))
    monkeypatch.setattr(main, "fetch_detail", lambda job: False)
    monkeypatch.setattr(main, "parse_attachments", lambda job, max_count=2: 0)
    monkeypatch.setattr(main.generate_html, "render", lambda *a, **k: None)
    monkeypatch.setattr(main, "resolve_pages_url", lambda: "")
    monkeypatch.setattr(main.notifier, "build_batch", lambda *a, **k: "B")
    monkeypatch.setattr(main.notifier, "push", lambda *a: True)
    summary = main.main(today=today)
    assert summary["new"] == 1
    assert len(saved["jobs"]) == 1


def test_main_attachment_parse_runs_for_direct_pdf(monkeypatch, make_job, today):
    job = make_job(title="天水市临床医学招聘", link="https://example.com/a.pdf",
                   deadline="2026-11-10", publish_date="2026-10-20")
    calls = []
    saved = {}

    def fake_parse(job, max_count=2):
        calls.append(job.link)
        return 1

    monkeypatch.setattr(main.storage, "load_history", lambda: {"jobs": []})
    monkeypatch.setattr(main.storage, "save_history", lambda data: saved.update(data))
    monkeypatch.setattr(main, "run_all", lambda return_report=False: (
        [job], [{"name": "s", "count": 1, "error": ""}]))
    monkeypatch.setattr(main, "fetch_detail", lambda job: False)
    monkeypatch.setattr(main, "parse_attachments", fake_parse)
    monkeypatch.setattr(main.generate_html, "render", lambda *a, **k: None)
    monkeypatch.setattr(main, "resolve_pages_url", lambda: "")
    monkeypatch.setattr(main.notifier, "build_batch", lambda *a, **k: "B")
    monkeypatch.setattr(main.notifier, "push", lambda *a: True)
    main.main(today=today)
    assert calls == ["https://example.com/a.pdf"]
    assert len(saved["jobs"]) == 1


def test_main_push_exception_is_swallowed(monkeypatch, make_job, today):
    job = _high_job(make_job)
    monkeypatch.setattr(main.storage, "load_history", lambda: {"jobs": []})
    monkeypatch.setattr(main.storage, "save_history", lambda data: None)
    monkeypatch.setattr(main, "run_all", lambda return_report=False: (
        [job], [{"name": "s", "count": 1, "error": ""}]))
    monkeypatch.setattr(main, "fetch_detail", lambda job: True)
    monkeypatch.setattr(main, "parse_attachments", lambda job, max_count=2: 0)
    monkeypatch.setattr(main.generate_html, "render", lambda *a, **k: None)
    monkeypatch.setattr(main, "resolve_pages_url", lambda: "")
    monkeypatch.setattr(main.notifier, "build_batch", lambda *a, **k: "B")

    def boom(*args):
        raise RuntimeError("push down")

    monkeypatch.setattr(main.notifier, "push", boom)
    summary = main.main(today=today)
    assert summary["new"] == 1


def test_prepare_history_splits_year_reused_url():
    a = {"title": "2025-2026学年度招聘公告", "link": "https://x/a",
         "fetched_at": "2026-09-01"}
    b = {"title": "2026-2027学年度招聘公告", "link": "https://x/a",
         "fetched_at": "2026-10-01"}
    history, = (main.prepare_history({"jobs": [a, b]}, "2026-11-03"),)
    assert len(history["jobs"]) == 2


def test_prepare_history_rejects_all_dropped():
    import pytest
    with pytest.raises(ValueError):
        main.prepare_history({"jobs": [1, "bad"]}, "2026-11-03")


def test_main_failed_detail_attempts_consume_cap(monkeypatch, make_job, today):
    jobs = [_high_job(make_job, link="https://example.com/1"),
            _high_job(make_job, link="https://example.com/2")]
    calls = []
    monkeypatch.setattr(main.storage, "load_history", lambda: {"jobs": []})
    monkeypatch.setattr(main.storage, "save_history", lambda data: None)
    monkeypatch.setattr(main, "run_all", lambda return_report=False: (
        jobs, [{"name": "s", "count": 2, "error": ""}]))
    monkeypatch.setattr(main, "MAX_DETAIL_FETCH", 1)
    monkeypatch.setattr(main, "fetch_detail", lambda job: calls.append(job.link) or False)
    monkeypatch.setattr(main, "parse_attachments", lambda job, max_count=2: 0)
    monkeypatch.setattr(main.generate_html, "render", lambda *a, **k: None)
    monkeypatch.setattr(main, "resolve_pages_url", lambda: "")
    monkeypatch.setattr(main.notifier, "build_batch", lambda *a, **k: "B")
    monkeypatch.setattr(main.notifier, "push", lambda *a: True)
    main.main(today=today)
    assert len(calls) == 1


def test_main_inferred_expired_gets_detail_deadline(monkeypatch, make_job, today):
    job = make_job(title="天水市临床医学招聘", link="https://example.com/old",
                   publish_date="2026-09-01", deadline="")

    def fake_detail(target):
        target.deadline = "2026-11-20"
        return True

    saved = {}
    monkeypatch.setattr(main.storage, "load_history", lambda: {"jobs": []})
    monkeypatch.setattr(main.storage, "save_history", lambda data: saved.update(data))
    monkeypatch.setattr(main, "run_all", lambda return_report=False: (
        [job], [{"name": "s", "count": 1, "error": ""}]))
    monkeypatch.setattr(main, "fetch_detail", fake_detail)
    monkeypatch.setattr(main, "parse_attachments", lambda job, max_count=2: 0)
    monkeypatch.setattr(main.generate_html, "render", lambda *a, **k: None)
    monkeypatch.setattr(main, "resolve_pages_url", lambda: "")
    monkeypatch.setattr(main.notifier, "build_batch", lambda *a, **k: "B")
    monkeypatch.setattr(main.notifier, "push", lambda *a: True)
    summary = main.main(today=today)
    assert summary["new"] == 1
    assert saved["jobs"][0]["status"] == "active"


def test_main_direct_attachment_score_zero_can_match(monkeypatch, make_job, today):
    job = make_job(title="某单位招聘公告", unit="", link="https://example.com/a.pdf",
                   publish_date="2026-10-20", deadline="")
    saved = {}
    monkeypatch.setattr(main.storage, "load_history", lambda: {"jobs": []})
    monkeypatch.setattr(main.storage, "save_history", lambda data: saved.update(data))
    monkeypatch.setattr(main, "run_all", lambda return_report=False: (
        [job], [{"name": "s", "count": 1, "error": ""}]))
    monkeypatch.setattr(main, "fetch_detail", lambda job: False)

    def fake_parse(target, max_count=2):
        target.major_req = "生物医学"
        return 1

    monkeypatch.setattr(main, "parse_attachments", fake_parse)
    monkeypatch.setattr(main.generate_html, "render", lambda *a, **k: None)
    monkeypatch.setattr(main, "resolve_pages_url", lambda: "")
    monkeypatch.setattr(main.notifier, "build_batch", lambda *a, **k: "B")
    monkeypatch.setattr(main.notifier, "push", lambda *a: True)
    summary = main.main(today=today)
    assert summary["new"] == 1
    assert saved["jobs"][0]["score"] == 5


def test_main_same_run_duplicate_merges_richer_deadline(monkeypatch, make_job, today):
    first = make_job(title="天水市临床医学招聘", link="https://example.com/same",
                     publish_date="2026-10-20", deadline="")
    second = make_job(title="天水市临床医学招聘（更新）", link="https://example.com/same/",
                      publish_date="2026-10-20", deadline="2026-11-30")
    saved = {}
    monkeypatch.setattr(main.storage, "load_history", lambda: {"jobs": []})
    monkeypatch.setattr(main.storage, "save_history", lambda data: saved.update(data))
    monkeypatch.setattr(main, "run_all", lambda return_report=False: (
        [first, second], [{"name": "s", "count": 2, "error": ""}]))
    monkeypatch.setattr(main, "fetch_detail", lambda job: False)
    monkeypatch.setattr(main, "parse_attachments", lambda job, max_count=2: 0)
    monkeypatch.setattr(main.generate_html, "render", lambda *a, **k: None)
    monkeypatch.setattr(main, "resolve_pages_url", lambda: "")
    monkeypatch.setattr(main.notifier, "build_batch", lambda *a, **k: "B")
    monkeypatch.setattr(main.notifier, "push", lambda *a: True)
    summary = main.main(today=today)
    assert summary["new"] == 1
    assert saved["jobs"][0]["deadline"] == "2026-11-30"
    assert saved["jobs"][0]["title"] == "天水市临床医学招聘（更新）"


def test_main_tolerates_corrupt_duplicate_fields(monkeypatch, today):
    raw = [
        {"title": "2026年招聘公告", "link": "https://example.com/x",
         "fetched_at": 123, "attachments": [{"bad": 1}], "score": 5},
        {"title": "2026年招聘公告", "link": "https://example.com/x/",
         "fetched_at": "2026-10-01", "attachments": [{"bad": 2}], "score": 5},
    ]
    monkeypatch.setattr(main.storage, "load_history", lambda: {"jobs": raw})
    monkeypatch.setattr(main.storage, "save_history", lambda data: None)
    monkeypatch.setattr(main.storage, "snapshot_history", lambda *a: "")
    monkeypatch.setattr(main, "run_all", lambda return_report=False: (
        [], [{"name": "s", "count": 0, "error": "x"}]))
    monkeypatch.setattr(main.generate_html, "render", lambda *a, **k: None)
    monkeypatch.setattr(main, "resolve_pages_url", lambda: "")
    monkeypatch.setattr(main.notifier, "push", lambda *a: True)
    main.main(today=today)

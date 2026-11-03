"""HTML 渲染与转义测试"""
import datetime

from generate_html import esc, render, render_detail, render_row, sort_key, status_badge


def test_esc_handles_zero_and_none():
    assert esc(0) == "0"
    assert esc(None) == ""
    assert esc('<script>alert(1)</script>') == "&lt;script&gt;alert(1)&lt;/script&gt;"
    assert esc('a&b"c') == "a&amp;b&quot;c"


def test_status_badge():
    assert "已过期" in status_badge("expired")
    assert "即将截止" in status_badge("expiring")
    assert "可报" in status_badge("active")
    assert "可报" in status_badge("unknown")


def test_sort_key_none_values():
    assert sort_key({"tier": None, "score": None, "days_left": None}) == (3, 1, 0, 999)
    assert sort_key({"tier": 1, "status": "expiring", "score": 8, "days_left": 0}) == (1, 0, -8, 0)


def test_render_detail_escapes_and_blocks_javascript():
    job = {
        "title": '<img src=x onerror=alert(1)>',
        "unit": '"><script>alert(2)</script>',
        "link": "javascript:alert(3)",
        "attachments": ["javascript:alert(4)", "https://example.com/a.pdf"],
        "match_explanation": ["<b>匹配</b>"],
        "salary_ref": "参考",
        "exam_advice": "行测",
    }
    html = render_detail(job)
    assert "<script>" not in html
    assert "onerror=" not in html
    assert "javascript:alert" not in html
    assert "https://example.com/a.pdf" in html


def test_render_row_zero_score_visible(make_job):
    job = make_job(score=0, days_left=0, status="active", deadline="", link="javascript:alert(1)")
    row = render_row(job.to_dict())
    assert ">0<" in row
    assert "javascript:" not in row
    assert "推定失效" in row


def test_render_writes_files_and_uses_resolved_pages_url(tmp_path):
    today = "2026-11-03"
    history = {"jobs": [
        {"title": "今日岗位", "link": "https://example.com/a", "score": 8,
         "tier": 1, "status": "active", "days_left": 5, "fetched_at": today,
         "unique_id": "a"},
        {"title": "历史岗位", "link": "https://example.com/b", "score": 3,
         "tier": 2, "status": "expired", "days_left": -2, "fetched_at": "2026-10-01",
         "unique_id": "b"},
    ]}
    out = tmp_path / "site" / "history.html"
    render(history, today, pages_url="https://example.github.io/repo/history.html", out_path=str(out))
    text = out.read_text(encoding="utf-8")
    assert "今日岗位" in text and "历史岗位" in text
    assert "https://example.github.io/repo/history.html" in text
    assert "Content-Security-Policy" in text
    assert "今日新增：<b>1</b>" in text
    assert "历史累计：<b>2</b>" in text
    assert (tmp_path / "site" / "index.html").exists()


def test_render_empty_daily_and_no_pages_url(tmp_path):
    history = {"jobs": [{"title": "旧岗位", "fetched_at": "2026-10-01", "tier": 1,
                         "score": 5, "status": "active", "days_left": 3,
                         "link": "https://example.com/a"}]}
    out = tmp_path / "history.html"
    render(history, "2026-11-03", pages_url="", out_path=str(out))
    text = out.read_text(encoding="utf-8")
    assert "今日无新增匹配岗位" in text
    assert "未配置 PAGES_URL" in text


def test_render_ignores_non_dict_jobs(tmp_path):
    out = tmp_path / "history.html"
    render({"jobs": ["bad", None, {"title": "ok", "link": "https://example.com"}]},
           "2026-11-03", pages_url="", out_path=str(out))
    assert "历史累计：<b>1</b>" in out.read_text(encoding="utf-8")


def test_render_with_date_object(tmp_path):
    out = tmp_path / "history.html"
    render({"jobs": []}, datetime.date(2026, 11, 3), pages_url="", out_path=str(out))
    assert "2026-11-03" in out.read_text(encoding="utf-8")


def test_render_detail_full_fields():
    job = {
        "title": "岗位",
        "link": "https://example.com/a",
        "salary_detail": "公告年薪 20 万",
        "salary_ref": "当地 5k-7k",
        "recruit_count": "3 人",
        "education": "硕士",
        "major_req": "生物医学",
        "job_requirements": "无犯罪记录",
        "background_check": "政审合格",
        "exam_subjects": "职业能力倾向测验",
        "exam_advice": "职测 E 类",
        "attachments": ["https://example.com/a.pdf"],
    }
    html = render_detail(job)
    for text in ("公告年薪 20 万", "3 人", "硕士", "生物医学",
                 "无犯罪记录", "政审合格", "职业能力倾向测验", "附件1"):
        assert text in html


def test_render_row_expiring_and_unknown_tier(make_job):
    job = make_job(status="expiring", days_left=2, tier=9, deadline="2026-11-05")
    row = render_row(job.to_dict())
    assert "即将截止" in row
    assert "t-tier-3" in row


def test_render_detail_tolerates_non_string_attachments():
    job = {"title": "岗位", "attachments": [{"x": 1}, 123, "javascript:alert(1)",
                                            "https://example.com/a.pdf"]}
    html = render_detail(job)
    assert "https://example.com/a.pdf" in html
    assert "javascript:" not in html


def test_render_row_shows_category(make_job):
    job = make_job(unit="", category="医学人才")
    assert "医学人才" in render_row(job.to_dict())

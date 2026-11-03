"""详情页字段与附件解析测试"""
import io

from bs4 import BeautifulSoup

import details


def test_is_attachment_url_with_query():
    assert details.is_attachment_url("https://x/a.pdf?download=1")
    assert details.is_attachment_url("https://x/a.XLSX")
    assert details.is_attachment_url("https://x/a.doc")
    assert not details.is_attachment_url("https://x/a.html")
    assert not details.is_attachment_url("")
    assert not details.is_attachment_url("javascript:alert(1)")


def test_extract_detail_fields_full():
    text = (
        "计划公开招聘 12 人。报考条件：具有中华人民共和国国籍，硕士及以上学历，"
        "生物医学相关专业。二、报名方式：报名时间：2026年11月1日至11月10日。"
        "纳入事业编制，年薪 20 万。考生须无犯罪记录。"
        "考试科目为职业能力倾向测验、综合应用能力。"
    )
    d = details.extract_detail_fields(text)
    assert d["recruit_count"] == "12 人"
    assert "国籍" in d["requirements"]
    assert d["deadline"] == "2026-11-10"
    assert "事业编制" in d["salary"]
    assert "无犯罪" in d["background_check"]
    assert d["exam_subjects"] == "职业能力倾向测验、综合应用能力"


def test_extract_detail_fields_deadline_variants():
    assert details.extract_detail_fields(
        "报名时间：2026-11-01 至 2026-11-10")["deadline"] == "2026-11-10"
    assert details.extract_detail_fields(
        "报名截止时间：2026年11月18日")["deadline"] == "2026-11-18"
    assert details.extract_detail_fields(
        "报名时间：2026年12月20日至1月5日")["deadline"] == "2027-01-05"


def test_extract_detail_fields_empty_and_no_match():
    assert details.extract_detail_fields("") == {
        "recruit_count": "", "requirements": "", "salary": "",
        "background_check": "", "exam_subjects": "", "deadline": "",
    }
    d = details.extract_detail_fields("没有任何结构化信息")
    assert d["recruit_count"] == ""
    assert d["deadline"] == ""


def test_sentences():
    assert details._sentences("A。B\nC；D; E") == ["A", "B", "C", "D", "E"]
    assert details._sentences("") == []


def test_body_text_prefers_selector_and_removes_script():
    html = ('<div class="article-content"><script>x</script>'
            '<p>正文内容</p></div><div>其他</div>')
    soup = BeautifulSoup(html, "lxml")
    text = details._body_text(soup, "事业单位招聘网")
    assert "正文内容" in text
    assert "x" not in text


def test_body_text_fallback_largest_block():
    html = "<div>" + "甲" * 250 + "</div><div>" + "乙" * 300 + "</div>"
    text = details._body_text(BeautifulSoup(html, "lxml"), "未知来源")
    assert "乙" in text


def test_fetch_detail_fills_fields_and_attachments(monkeypatch, fake_response, make_job):
    html = """
    <div class="article-content">
      计划招聘 5 人。报名截止时间：2026年11月18日。
      <a href="/files/岗位表.xlsx">岗位表</a>
      <a href="/files/公告.pdf?download=1">公告 PDF</a>
      <a href="javascript:alert(1)">坏链接</a>
    </div>"""
    calls = []

    def fake_get(url, **kwargs):
        calls.append(kwargs)
        return fake_response(text=html)

    monkeypatch.setattr(details, "http_get", fake_get)
    job = make_job(source="事业单位招聘网", title="招聘公告", link="https://example.com/a.html", deadline="")
    assert details.fetch_detail(job) is True
    assert job.recruit_count == "5 人"
    assert job.deadline == "2026-11-18"
    assert any("岗位表.xlsx" in a for a in job.attachments)
    assert any("公告.pdf" in a for a in job.attachments)
    assert all("javascript:" not in a for a in job.attachments)
    assert calls[0]["encoding"] == "gbk"


def test_fetch_detail_failure(monkeypatch, make_job):
    def fake_get(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(details, "http_get", fake_get)
    job = make_job()
    assert details.fetch_detail(job) is False


def test_fetch_detail_skips_attachment_link(make_job):
    job = make_job(link="https://example.com/a.pdf")
    assert details.fetch_detail(job) is False


def test_parse_attachments_applies_text(monkeypatch, make_job):
    calls = []

    def fake_text(url):
        calls.append(url)
        return "某某市人民医院 硕士 生物医学"

    monkeypatch.setattr(details, "extract_attachment_text", fake_text)
    job = make_job(link="https://example.com/a.pdf?x=1", unit="", major_req="", education="")
    assert details.parse_attachments(job, max_count=1) == 1
    assert calls == ["https://example.com/a.pdf?x=1"]
    assert job.major_req.startswith("某某市人民医院")
    assert job.education == "硕士"
    assert job.unit == "某某市人民医院"


def test_parse_attachments_limits_and_dedupes(monkeypatch, make_job):
    urls = []
    monkeypatch.setattr(details, "extract_attachment_text",
                        lambda url: urls.append(url) or "文本")
    job = make_job(link="", attachments=[
        "https://x/a.pdf", "https://x/a.pdf", "https://x/b.xlsx", "https://x/c.html",
    ])
    assert details.parse_attachments(job, max_count=2) == 2
    assert urls == ["https://x/a.pdf", "https://x/b.xlsx"]
    assert details.try_extract_attachment(job) == 2


def test_apply_attachment_text_does_not_overwrite(make_job):
    job = make_job(major_req="已有", education="博士", unit="已有单位")
    assert details.apply_attachment_text(job, "硕士 生物医学 某医院") is True
    assert job.major_req == "已有"
    assert job.education == "博士"
    assert job.unit == "已有单位"


def test_xlsx_text_roundtrip():
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["岗位", "专业"])
    ws.append(["医院", "生物医学"])
    buf = io.BytesIO()
    wb.save(buf)
    text = details._xlsx_text(buf.getvalue())
    assert "生物医学" in text
    assert "岗位" in text


def test_extract_attachment_text_dispatch(monkeypatch):
    monkeypatch.setattr(details, "http_download", lambda url, **kwargs: b"data")
    monkeypatch.setattr(details, "_xlsx_text", lambda data: "xlsx")
    monkeypatch.setattr(details, "_xls_text", lambda data: "xls")
    monkeypatch.setattr(details, "_pdf_text", lambda data: "pdf")
    assert details.extract_attachment_text("https://x/a.xlsx") == "xlsx"
    assert details.extract_attachment_text("https://x/a.xls") == "xls"
    assert details.extract_attachment_text("https://x/a.pdf") == "pdf"
    assert details.extract_attachment_text("https://x/a.docx") == ""


def test_extract_attachment_text_swallows_errors(monkeypatch):
    monkeypatch.setattr(details, "http_download", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert details.extract_attachment_text("https://x/a.pdf") == ""


def test_deadline_separators_and_yearless():
    assert details.extract_detail_fields(
        "报名时间：2026年11月1日-11月10日")["deadline"] == "2026-11-10"
    assert details.extract_detail_fields(
        "报名时间：2026年11月1日－11月10日")["deadline"] == "2026-11-10"
    import datetime
    year = datetime.date.today().year
    assert details.extract_detail_fields(
        "报名时间：11月1日至11月10日")["deadline"] == f"{year}-11-10"


def test_fetch_detail_reader_markdown_attachments(monkeypatch, fake_response, make_job):
    response = fake_response(text="公告正文\n\n[岗位表](https://example.com/a.xlsx)")
    response.is_markdown = True
    monkeypatch.setattr(details, "http_get", lambda *a, **k: response)
    job = make_job(link="https://example.com/a.html")
    assert details.fetch_detail(job) is True
    assert job.attachments == ["https://example.com/a.xlsx"]


def test_parse_attachments_skips_docx_slots(monkeypatch, make_job):
    urls = []
    monkeypatch.setattr(details, "extract_attachment_text",
                        lambda url: urls.append(url) or "文本")
    job = make_job(link="", attachments=[
        "https://x/a.docx", "https://x/b.pdf", "https://x/c.xlsx",
    ])
    assert details.parse_attachments(job, max_count=2) == 2
    assert urls == ["https://x/b.pdf", "https://x/c.xlsx"]

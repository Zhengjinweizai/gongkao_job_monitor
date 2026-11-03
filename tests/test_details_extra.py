"""详情/附件解析的额外分支"""
import sys
import types

from bs4 import BeautifulSoup

import details


def test_pdf_text(monkeypatch):
    class Page:
        def extract_text(self):
            return "PDF 文本"

    class Reader:
        def __init__(self, *args, **kwargs):
            self.pages = [Page()]

    monkeypatch.setitem(sys.modules, "pypdf", types.SimpleNamespace(PdfReader=Reader))
    assert "PDF 文本" in details._pdf_text(b"data")


def test_xls_text(monkeypatch):
    class Sheet:
        nrows = 2

        def row_values(self, index):
            return ["岗位", "生物医学"] if index == 0 else ["医院", "硕士"]

    class Book:
        def sheets(self):
            return [Sheet()]

    monkeypatch.setitem(sys.modules, "xlrd",
                        types.SimpleNamespace(open_workbook=lambda **kwargs: Book()))
    text = details._xls_text(b"data")
    assert "生物医学" in text
    assert "硕士" in text


def test_fetch_detail_title_count_fallback(monkeypatch, fake_response, make_job):
    monkeypatch.setattr(details, "http_get", lambda *a, **k: fake_response(
        text='<div class="article-content">公告正文没有人数信息</div>'))
    job = make_job(title="某某医院招聘（5人）", source="其他", link="https://x/a.html")
    assert details.fetch_detail(job) is True
    assert job.recruit_count == "5 人"


def test_fetch_detail_empty_body(monkeypatch, fake_response, make_job):
    monkeypatch.setattr(details, "http_get", lambda *a, **k: fake_response(text=""))
    job = make_job(link="https://x/a.html")
    assert details.fetch_detail(job) is False


def test_body_text_whole_soup_fallback():
    soup = BeautifulSoup("<p>短文本</p>", "lxml")
    assert "短文本" in details._body_text(soup, "未知")


def test_parse_attachments_empty(make_job):
    job = make_job(link="", attachments=[])
    assert details.parse_attachments(job) == 0


def test_apply_attachment_text_empty(make_job):
    job = make_job()
    assert details.apply_attachment_text(job, "") is False
    assert details.apply_attachment_text(job, None) is False


def test_extract_detail_fields_salary_dedupe():
    text = "纳入事业编制。纳入事业编制。年薪 20 万。"
    d = details.extract_detail_fields(text)
    assert d["salary"].count("纳入事业编制") == 1

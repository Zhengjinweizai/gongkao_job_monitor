"""详情页字段提取与附件解析"""
import datetime
import io
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from config import (
    ATTACHMENT_TIMEOUT,
    DETAIL_TIMEOUT,
    MAX_ATTACHMENT_BYTES,
    PARSE_ATTACHMENT,
)
from http_client import http_download, http_get
from utils import log, safe_url

ATTACHMENT_SUFFIXES = (".pdf", ".xls", ".xlsx", ".doc", ".docx")
PARSEABLE_SUFFIXES = (".pdf", ".xls", ".xlsx")

BODY_SELECTORS = {
    "事业单位招聘网": [".article-content", "div.content", "article", "#content", ".news-content", ".con-libox"],
    "高校人才网": [".article-content", ".announcement-content", ".detail-content", "article", "#content", ".content"],
    "甘肃组工网": ["#content", ".TRS_Editor", "article", ".con", ".detail"],
    "中国公共招聘网": ["#content", ".article", ".detail", ".news-content"],
    "甘肃省人社厅": ["#content", ".TRS_Editor", "article"],
    "陕西省人社厅": ["#content", ".TRS_Editor", "article"],
    "西安人事考试网": ["#content", ".article", ".detail"],
    "国家公务员局": ["#content", "article", ".main"],
    "测试": ["body"],
}

# 支持 2026年11月1日 / 2026-11-01 / 2026/11/1 / 2026.11.1
DATE_PART = r"(20\d{2})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})\s*[日号]?"


def is_attachment_url(url):
    if not isinstance(url, str):
        return False
    try:
        path = urlsplit(url).path.lower()
    except ValueError:
        return False
    return path.endswith(ATTACHMENT_SUFFIXES)


def _body_text(soup, source):
    for sel in BODY_SELECTORS.get(source, []):
        el = soup.select_one(sel)
        if el:
            for tag in el(["script", "style"]):
                tag.decompose()
            return el.get_text("\n", strip=True)[:15000]
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    blocks = [b for b in soup.find_all(["div", "article", "section"])
              if len(b.get_text(strip=True)) > 200]
    if blocks:
        best = max(blocks, key=lambda b: len(b.get_text(strip=True)))
        return best.get_text("\n", strip=True)[:15000]
    return soup.get_text("\n", strip=True)[:15000]


def _sentences(text):
    parts = re.split(r"[。\n；;]", text or "")
    return [p.strip() for p in parts if p.strip()]


def _date_from_groups(year, month, day):
    try:
        return datetime.date(int(year), int(month), int(day))
    except ValueError:
        return None


RANGE_SEP = r"(?:至|—|－|到|截止|止|-|~|～)"


def _deadline_from_text(text):
    # “2026年11月1日至11月10日” / “2026-11-01 至 2026-11-10” / “...-11月10日”
    m = re.search(
        r"报名(?:时间|时段)?[^。\n]{0,40}?" + DATE_PART +
        r".{0,60}?" + RANGE_SEP + r".{0,15}?"
        r"(?:(20\d{2})\s*[年./-]\s*)?(\d{1,2})\s*[月./-]\s*(\d{1,2})\s*[日号]?",
        text, re.S)
    if m:
        start = _date_from_groups(m.group(1), m.group(2), m.group(3))
        year = m.group(4) or m.group(1)
        end = _date_from_groups(year, m.group(5), m.group(6))
        if start and end:
            if end < start and not m.group(4):
                end = _date_from_groups(int(year) + 1, m.group(5), m.group(6))
            if end:
                return end.isoformat()
    # 起始日期不带年份：“11月1日至11月10日”
    m = re.search(
        r"报名(?:时间|时段)?[^。\n]{0,40}?(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?"
        r".{0,60}?" + RANGE_SEP + r".{0,15}?"
        r"(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?",
        text, re.S)
    if m:
        year = m.group(3) or str(datetime.date.today().year)
        start = _date_from_groups(year, m.group(1), m.group(2))
        end = _date_from_groups(year, m.group(4), m.group(5))
        if start and end:
            if end < start and not m.group(3):
                end = _date_from_groups(int(year) + 1, m.group(4), m.group(5))
            if end:
                return end.isoformat()
    m = re.search(
        r"(?:报名截止|截止时间|报名时间截止|截止日期)[^0-9]{0,10}" + DATE_PART, text)
    if m:
        end = _date_from_groups(m.group(1), m.group(2), m.group(3))
        if end:
            return end.isoformat()
    m = re.search(
        r"(?:报名截止|截止时间|报名时间截止|截止日期)[^0-9]{0,10}"
        r"(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?", text)
    if m:
        year = m.group(1) or str(datetime.date.today().year)
        end = _date_from_groups(year, m.group(2), m.group(3))
        if end:
            return end.isoformat()
    return ""


def extract_detail_fields(text):
    d = {"recruit_count": "", "requirements": "", "salary": "",
         "background_check": "", "exam_subjects": "", "deadline": ""}
    if not text:
        return d
    for pat in (r"计划公开招聘\s*([0-9]+)\s*[人名]",
                r"公开招聘\s*(?:工作人员|专业技术人员|教师|管理人员|工作)?\s*([0-9]+)\s*[人名]",
                r"计划招聘\s*([0-9]+)\s*人",
                r"招聘\s*([0-9]+)\s*[人名]",
                r"引进\s*([0-9]+)\s*名",
                r"招录\s*([0-9]+)\s*人"):
        m = re.search(pat, text)
        if m:
            d["recruit_count"] = m.group(1) + " 人"
            break
    m = re.search(r"(?:报考条件|招聘条件|报名条件|应聘条件|招聘范围及条件|岗位要求)\s*[：:]?(.{0,500}?)(?=二、|三、|四、|五、|六、|\n\n)", text, re.S)
    if m:
        d["requirements"] = re.sub(r"\s+", " ", m.group(1)).strip()[:300]
    sents = _sentences(text)
    sal = [s for s in sents if any(k in s for k in
           ("安家费", "年薪", "月薪", "薪酬", "工资待遇", "工资福利", "纳入编制",
            "事业编制", "编制内", "绩效工资", "人才补贴"))]
    if sal:
        d["salary"] = "；".join(dict.fromkeys(sal))[:300]
    bc = [s for s in sents if any(k in s for k in
          ("政审", "考察环节", "无犯罪", "犯罪记录", "失信", "征信", "背调", "政治审查"))]
    if bc:
        d["background_check"] = "；".join(dict.fromkeys(bc))[:300]
    subs = [k for k in ("行政职业能力测验", "申论", "职业能力倾向测验",
                        "综合应用能力", "公共基础知识", "专业科目", "面试") if k in text]
    if subs:
        d["exam_subjects"] = "、".join(subs)
    d["deadline"] = _deadline_from_text(text)
    return d


def fetch_detail(job):
    """抓取公告详情；返回是否成功拿到正文（用于详情配额计数）。"""
    if not job.link or is_attachment_url(job.link):
        return False
    try:
        encoding = "gbk" if job.source == "事业单位招聘网" else None
        response = http_get(job.link, timeout=DETAIL_TIMEOUT, encoding=encoding)
        html = response.text
    except Exception as e:
        log(f"[详情] 抓取失败 {job.link}: {e}")
        return False
    if not html:
        return False
    soup = BeautifulSoup(html, "lxml")
    text = _body_text(soup, job.source)
    if not text:
        return False
    d = extract_detail_fields(text)
    if d["deadline"] and not job.deadline:
        job.deadline = d["deadline"]
    if d["recruit_count"] and not job.recruit_count:
        job.recruit_count = d["recruit_count"]
    if d["requirements"] and not job.job_requirements:
        job.job_requirements = d["requirements"]
    if d["salary"] and not job.salary_detail:
        job.salary_detail = d["salary"]
    if d["background_check"] and not job.background_check:
        job.background_check = d["background_check"]
    if d["exam_subjects"] and not job.exam_subjects:
        job.exam_subjects = d["exam_subjects"]
    if not job.recruit_count:
        m = re.search(r"[（(]([0-9]+)\s*(?:人|名)[)）]", job.title or "")
        if m:
            job.recruit_count = m.group(1) + " 人"
    atts = []
    for a in soup.find_all("a", href=True):
        url = urljoin(job.link, a.get("href") or "")
        if is_attachment_url(url):
            safe = safe_url(url)
            if safe:
                atts.append(safe)
    # Reader 兜底返回的是 markdown，附件链接不是 <a> 标签
    if getattr(response, "is_markdown", False):
        for m in re.finditer(r"\[[^\]]+\]\((https?://[^)\s]+)\)", html):
            url = safe_url(m.group(1))
            if is_attachment_url(url):
                atts.append(url)
    if atts:
        merged = list(dict.fromkeys(list(job.attachments or []) + atts))
        job.attachments = merged[:5]
    log(f"[详情] {job.title[:24]}... 提取完成（人数={job.recruit_count or '-'} 截止={job.deadline or '-'} 科目={job.exam_subjects or '-'}）")
    return True


def _pdf_text(data):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    text = ""
    for page in reader.pages[:5]:
        text += (page.extract_text() or "") + "\n"
    return text[:3000]


def _xlsx_text(data):
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    parts = []
    try:
        for ws in wb.worksheets[:3]:
            for row in ws.iter_rows(max_row=200, max_col=30, values_only=True):
                vals = [str(v).strip() for v in row if v is not None and str(v).strip()]
                if vals:
                    parts.append(" | ".join(vals))
    finally:
        wb.close()
    return "\n".join(parts)[:3000]


def _xls_text(data):
    import xlrd
    book = xlrd.open_workbook(file_contents=data)
    parts = []
    for sheet in book.sheets()[:3]:
        for row_idx in range(min(sheet.nrows, 200)):
            vals = [str(v).strip() for v in sheet.row_values(row_idx)
                    if str(v).strip()]
            if vals:
                parts.append(" | ".join(vals))
    return "\n".join(parts)[:3000]


def extract_attachment_text(url):
    if not isinstance(url, str):
        return ""
    try:
        suffix = urlsplit(url).path.lower()
    except ValueError:
        return ""
    try:
        if suffix.endswith(".pdf"):
            return _pdf_text(http_download(url, timeout=ATTACHMENT_TIMEOUT, max_bytes=MAX_ATTACHMENT_BYTES))
        if suffix.endswith(".xlsx"):
            return _xlsx_text(http_download(url, timeout=ATTACHMENT_TIMEOUT, max_bytes=MAX_ATTACHMENT_BYTES))
        if suffix.endswith(".xls"):
            return _xls_text(http_download(url, timeout=ATTACHMENT_TIMEOUT, max_bytes=MAX_ATTACHMENT_BYTES))
    except Exception as e:
        log(f"[附件] {safe_url(url)} 解析失败: {e}")
    return ""


def apply_attachment_text(job, text):
    text = (text or "").strip()
    if not text:
        return False
    if not job.major_req:
        job.major_req = text[:300]
    if not job.education:
        if "硕士" in text:
            job.education = "硕士"
        elif "博士" in text:
            job.education = "博士"
        elif "本科" in text:
            job.education = "本科及以上"
    if not job.unit:
        m = re.search(r"([\u4e00-\u9fa5]{2,20}(?:局|中心|医院|委员会|学校|学院|大学))", text)
        if m:
            job.unit = m.group(1)
    return True


def parse_attachments(job, max_count=2):
    """解析公告内收集到的岗位表附件（PDF/Excel），返回成功解析数量。"""
    if not PARSE_ATTACHMENT:
        return 0
    urls = []
    if is_attachment_url(job.link):
        urls.append(job.link)
    urls.extend(u for u in (job.attachments or []) if isinstance(u, str))
    seen = []
    for url in urls:
        if not isinstance(url, str):
            continue
        try:
            path = urlsplit(url).path.lower()
        except ValueError:
            continue
        if path.endswith(PARSEABLE_SUFFIXES) and url not in seen:
            seen.append(url)
    parsed = 0
    for url in seen[:max_count]:
        text = extract_attachment_text(url)
        if apply_attachment_text(job, text):
            parsed += 1
    return parsed


def try_extract_attachment(job):
    """兼容旧调用：返回成功解析的附件数。"""
    return parse_attachments(job)

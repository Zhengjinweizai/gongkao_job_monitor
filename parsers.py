"""全部招聘公告解析器（合一文件）"""
import random
import re
import time
import datetime
from dataclasses import dataclass, field, asdict
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from config import SOURCES, PARSE_ATTACHMENT


@dataclass
class Job:
    title: str = ""
    unit: str = ""
    location: str = ""
    province: str = ""
    city: str = ""
    education: str = ""
    major_req: str = ""
    deadline: str = ""
    link: str = ""
    source: str = ""
    publish_date: str = ""
    score: int = 0
    region_score: int = 0
    major_score: int = 0
    region_label: str = ""
    major_kind: str = "none"
    major_hits: list = field(default_factory=list)
    match_points: str = ""
    exam_advice: str = ""
    salary_ref: str = ""
    status: str = "active"
    days_left: int = 0
    recruit_count: str = ""
    job_requirements: str = ""
    salary_detail: str = ""
    background_check: str = ""
    exam_subjects: str = ""
    attachments: list = field(default_factory=list)
    match_explanation: list = field(default_factory=list)
    suggestion: str = ""

    def unique_id(self):
        raw = f"{self.unit}|{self.title}|{self.publish_date}|{self.link}"
        return __import__("hashlib").md5(raw.encode("utf-8")).hexdigest()

    def to_dict(self):
        d = asdict(self)
        d["unique_id"] = self.unique_id()
        return d


# ============ 基础工具 ============
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
]


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def polite_delay():
    time.sleep(random.uniform(1.0, 3.0))


def http_get(url, timeout=20, encoding=None, headers=None):
    h = headers or {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Connection": "keep-alive",
    }
    r = requests.get(url, headers=h, timeout=timeout)
    r.raise_for_status()
    if encoding:
        r.encoding = encoding
    return r


ANNO_KEYWORDS = ["招聘", "招录", "考录", "选调", "遴选", "聘用",
                 "招募", "补充公告", "拟录用", "公示", "公告"]

NEGATIVE_KEYWORDS = ["大赛", "吉祥物", "征集", "评选", "表彰", "奖项", "奖牌",
                     "比赛", "竞赛", "预算", "决算", "采购", "中标", "成交",
                     "讲座", "培训会", "活动", "征文", "招募令", "志愿者",
                     "成果奖", "审查结果", "课题", "评估", "普查", "任前公示",
                     "拟录用", "拟聘用", "拟录取", "体检", "录取", "录用名单",
                     "结果查询", "结果公示", "成绩查询", "分数线", "资格复审",
                     "面试通知", "进入体检", "考察公告", "考察通知", "递补"]


def extract_announcements(html, base_url, keep_words=None, limit=60):
    keep_words = keep_words or ANNO_KEYWORDS
    soup = BeautifulSoup(html, "lxml")
    seen, items = set(), []
    for a in soup.find_all("a", href=True):
        text = (a.get_text() or "").strip().replace("\n", "").replace("\u3000", " ").strip()
        href = (a.get("href") or "").strip()
        if len(text) < 8 or len(text) > 120:
            continue
        low = href.lower()
        if any(x in low for x in (".css", ".js", ".png", ".jpg", ".gif", ".jpeg",
                                  "#", "javascript:", "mailto:", ".ico")):
            continue
        if any(k in text for k in NEGATIVE_KEYWORDS):
            continue
        if not any(k in text for k in keep_words):
            continue
        link = urljoin(base_url, href)
        if link in seen:
            continue
        seen.add(link)
        items.append({"title": text, "link": link})
        if len(items) >= limit:
            break
    return items


def extract_date(text):
    text = text or ""
    m = re.search(r"(\d{4})\s*年?\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if m:
        try:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            pass
    m = re.search(r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})", text)
    if m:
        try:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            pass
    return ""


# ============ 1. 国家公务员局（国考） ============
def _fetch_guokao():
    url = SOURCES["guokao"]["url"]
    jobs = []
    try:
        html = http_get(url, timeout=15).text
        for it in extract_announcements(html, url, limit=30):
            if any(k in it["title"] for k in ("公务员", "招录", "考录", "补充录用", "调剂")):
                jobs.append(Job(title=it["title"], unit="国家公务员局", link=it["link"],
                                source="国家公务员局", publish_date=extract_date(it["title"])))
        polite_delay()
    except Exception as e:
        log(f"[国考] 抓取失败: {e}")
    return jobs


# ============ 2. 甘肃组工网（省考/选调） ============
def _fetch_gszg():
    url = SOURCES["gszg"]["url"]
    jobs = []
    try:
        html = http_get(url).text
        for it in extract_announcements(html, url):
            jobs.append(Job(title=it["title"], unit="甘肃组工网", link=it["link"],
                            source="甘肃组工网", publish_date=extract_date(it["title"])))
        polite_delay()
    except Exception as e:
        log(f"[甘肃组工网] 抓取失败: {e}")
    return jobs


# ============ 3. 甘肃省人社厅 ============
def _fetch_gansu_hr():
    urls = [SOURCES["gansu_hr"]["url"],
            "http://rst.gansu.gov.cn",
            "https://rst.gansu.gov.cn/rst/"]
    jobs = []
    for url in urls:
        try:
            html = http_get(url).text
            items = extract_announcements(html, url)
            if items:
                jobs = [Job(title=it["title"], unit="甘肃省人社厅", link=it["link"],
                            source="甘肃省人社厅", publish_date=extract_date(it["title"]))
                        for it in items]
                break
        except Exception as e:
            log(f"[甘肃省人社厅] {url} 抓取失败: {e}")
            polite_delay()
    return jobs


# ============ 4. 西安人事考试网（JS动态，playwright 兜底） ============
def _fetch_xapta():
    url = SOURCES["xapta"]["url"]
    try:
        html = http_get(url).text
        if html and len(html) > 2000:
            items = extract_announcements(html, url)
            if items:
                return [_to_job(it, "西安人事考试网") for it in items]
    except Exception as e:
        log(f"[西安人事考试网] requests 失败: {e}")
    return _xapta_playwright(url)


def _to_job(it, source):
    return Job(title=it["title"], unit=source, link=it["link"],
               source=source, publish_date=extract_date(it["title"]))


def _xapta_playwright(url):
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        log(f"[西安人事考试网] playwright 未安装，跳过: {e}")
        return []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=random.choice(USER_AGENTS))
            page.goto(url, timeout=30000)
            page.wait_for_timeout(3000)
            html = page.content()
            browser.close()
        items = extract_announcements(html, url)
        return [_to_job(it, "西安人事考试网") for it in items]
    except Exception as e:
        log(f"[西安人事考试网] playwright 抓取失败: {e}")
        return []


# ============ 5. 陕西省人社厅 ============
def _fetch_shaanxi():
    url = SOURCES["shaanxi"]["url"]
    jobs = []
    try:
        html = http_get(url).text
        for it in extract_announcements(html, url):
            jobs.append(Job(title=it["title"], unit="陕西省人社厅", link=it["link"],
                            source="陕西省人社厅", publish_date=extract_date(it["title"])))
        polite_delay()
    except Exception as e:
        log(f"[陕西省人社厅] 抓取失败: {e}")
    return jobs


# ============ 6. 中国公共招聘网（人社部官方，JSON 接口优先） ============
MOHRSS_API = "https://job.mohrss.gov.cn/cjobs/institution/getinstitutionbyajax"


def _fetch_mohrss():
    jobs = []
    try:
        r = requests.post(MOHRSS_API, headers={
            "User-Agent": random.choice(USER_AGENTS),
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://job.mohrss.gov.cn/",
        }, timeout=20)
        data = r.json()
        for item in data:
            title = item.get("title") or ""
            cid = item.get("contentId") or ""
            renshu = item.get("renshu") or ""
            if not title or not cid:
                continue
            link = f"https://job.mohrss.gov.cn/sydwgg/{cid}/.jhtml"
            if renshu:
                title = f"{title}（{renshu}）"
            jobs.append(Job(title=title, unit="", link=link,
                            source="中国公共招聘网", publish_date=extract_date(title)))
        log(f"[中国公共招聘网] JSON 接口返回 {len(jobs)} 条")
        if jobs:
            return jobs
    except Exception as e:
        log(f"[中国公共招聘网] JSON 接口失败: {e}")
    try:
        url = "https://job.mohrss.gov.cn/cjobs/institution/listInstitution?pageNo=1"
        html = http_get(url).text
        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            text = (a.get_text() or "").strip()
            href = a.get("href") or ""
            if len(text) < 8 or "javascript" in href:
                continue
            if not any(k in text for k in ("招聘", "招录", "聘用")):
                continue
            jobs.append(Job(title=text, unit="", link=urljoin(url, href),
                            source="中国公共招聘网", publish_date=extract_date(text)))
        polite_delay()
    except Exception as e:
        log(f"[中国公共招聘网] 列表页兜底失败: {e}")
    return jobs


# ============ 7. 事业单位招聘网（GBK 聚合源，覆盖全国） ============
EN_PROVINCE = {
    "gansu": "甘肃", "shanxisheng": "陕西", "shanxi": "山西", "sichuan": "四川",
    "shandong": "山东", "jiangsu": "江苏", "zhejiang": "浙江", "guangdong": "广东",
    "guangxi": "广西", "hunan": "湖南", "hubei": "湖北", "henan": "河南",
    "hebei": "河北", "beijing": "北京", "shanghai": "上海", "tianjin": "天津",
    "chongqing": "重庆", "fujian": "福建", "jiangxi": "江西", "anhui": "安徽",
    "yunnan": "云南", "guizhou": "贵州", "neimenggu": "内蒙古", "ningxia": "宁夏",
    "qinghai": "青海", "hainan": "海南", "xinjiang": "新疆", "jilin": "吉林",
    "liaoning": "辽宁", "heilongjiang": "黑龙江", "xizang": "西藏",
}


def _province_from_path(path):
    for en, zh in EN_PROVINCE.items():
        if en in path:
            return zh
    return ""


def _combine_md(md, today, title=""):
    md = md.strip()
    m = re.search(r"(\d{1,2})-(\d{1,2})", md)
    if not m:
        return ""
    month, day = int(m.group(1)), int(m.group(2))
    year = today.year
    m2 = re.search(r"(20\d{2})\s*年", title or "")
    if m2:
        year = int(m2.group(1))
    elif month > today.month:
        year -= 1
    try:
        return datetime.date(year, month, day).isoformat()
    except ValueError:
        return ""


def _fetch_shiyebian():
    today = datetime.date.today()
    jobs = []
    urls = ["https://www.shiyebian.net/",
            "https://www.shiyebian.net/gansu/",
            "https://www.shiyebian.net/shanxisheng/"]
    for url in urls:
        try:
            r = http_get(url, encoding="gbk")
            soup = BeautifulSoup(r.text, "lxml")
            ul = soup.select_one("ul.list-index")
            if not ul:
                continue
            for li in ul.select("li"):
                em = li.find("em")
                date_md = em.get_text(strip=True) if em else ""
                links = li.find_all("a", href=True)
                if len(links) < 2:
                    continue
                region_a = links[0]
                title_a = links[-1]
                title = (title_a.get_text() or "").strip()
                link = urljoin(url, title_a.get("href") or "")
                if not title or len(title) < 8:
                    continue
                region_path = region_a.get("href") or ""
                province = _province_from_path(region_path)
                city = (region_a.get_text() or "").strip()
                publish_date = extract_date(title) or _combine_md(date_md, today, title)
                jobs.append(Job(title=title, unit="", location=f"{province}{city}",
                                province=province, city=city, link=link,
                                source="事业单位招聘网", publish_date=publish_date))
            polite_delay()
        except Exception as e:
            log(f"[事业单位招聘网] 抓取 {url} 失败: {e}")
    return jobs


# ============ 8. 高校人才网（高校/中小学校/医卫院校等事业单位范畴） ============
GAOXIAOJOB_PAGES = [
    ("https://www.gaoxiaojob.com/column/38.html", "甘肃"),
    ("https://www.gaoxiaojob.com/column/37.html", "陕西"),
    ("https://www.gaoxiaojob.com/column/50.html", "西安"),
    ("https://www.gaoxiaojob.com/column/107.html", "兰州"),
    ("https://www.gaoxiaojob.com/column/1.html", "高校招聘"),
    ("https://www.gaoxiaojob.com/column/2.html", "中小学校"),
    ("https://www.gaoxiaojob.com/column/5.html", "医学人才"),
    ("https://www.gaoxiaojob.com/column/4.html", "政府与事业单位"),
]

GAOXIAOJOB_KEEP = ["招聘", "招录", "选调", "人才引进", "引进", "招募", "招"]


def _fetch_gaoxiaojob():
    jobs = []
    seen = set()
    for url, label in GAOXIAOJOB_PAGES:
        try:
            html = http_get(url).text
            for it in extract_announcements(html, url, keep_words=GAOXIAOJOB_KEEP, limit=50):
                link = it["link"]
                if "/announcement/detail/" not in link:
                    continue
                if link in seen:
                    continue
                seen.add(link)
                title = it["title"].split("：", 1)[-1] if "：" in it["title"] else it["title"]
                job = Job(title=title, unit=label, link=link,
                          source="高校人才网", publish_date=extract_date(it["title"]))
                if label in ("甘肃", "陕西", "西安", "兰州"):
                    job.location = label
                jobs.append(job)
            polite_delay()
        except Exception as e:
            log(f"[高校人才网] {url} 抓取失败: {e}")
    return jobs


# ============ 详情页提取（薪资/条件/政审/截止/科目/附件） ============
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
    parts = re.split(r"[。\n；;]", text)
    return [p.strip() for p in parts if p.strip()]


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
    m = re.search(r"报名(?:时间|时段)?[^0-9]{0,10}(20\d{2}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日).{0,50}?(?:至|—|到|截止|止).{0,10}(20\d{2}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)", text)
    if m:
        d["deadline"] = extract_date(m.group(2))
    else:
        m = re.search(r"(?:报名截止|截止时间|报名时间截止|截止日期)[^0-9]{0,10}(20\d{2}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)", text)
        if m:
            d["deadline"] = extract_date(m.group(1))
    return d


def fetch_detail(job):
    if not job.link:
        return
    try:
        html = http_get(job.link, timeout=15,
                        encoding="gbk" if job.source == "事业单位招聘网" else None).text
    except Exception as e:
        log(f"[详情] 抓取失败 {job.link}: {e}")
        return
    soup = BeautifulSoup(html, "lxml")
    text = _body_text(soup, job.source)
    if not text:
        return
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
        href = (a.get("href") or "").lower()
        if re.search(r"\.(pdf|xlsx?|docx?)(\?.*)?$", href):
            atts.append(urljoin(job.link, a.get("href")))
    if atts:
        job.attachments = list(dict.fromkeys(atts))[:5]
    log(f"[详情] {job.title[:24]}... 提取完成（人数={job.recruit_count or '-'} 截止={job.deadline or '-'} 科目={job.exam_subjects or '-'}）")


# ============ 附件解析（Excel / PDF） ============
def _download_binary(url):
    h = {"User-Agent": random.choice(USER_AGENTS)}
    r = requests.get(url, headers=h, timeout=30)
    r.raise_for_status()
    return r.content


def _pdf_text(url):
    from pypdf import PdfReader
    import io
    reader = PdfReader(io.BytesIO(_download_binary(url)))
    text = ""
    for page in reader.pages[:5]:
        text += (page.extract_text() or "") + "\n"
    return text[:3000]


def _excel_text(url):
    import pandas as pd
    import io
    data = _download_binary(url)
    sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, dtype=str)
    parts = []
    for df in sheets.values():
        parts.append(df.head(200).to_string(index=False))
    return "\n".join(parts)[:3000]


def try_extract_attachment(job):
    if not PARSE_ATTACHMENT or not job.link:
        return
    low = job.link.lower()
    try:
        if low.endswith(".pdf"):
            text = _pdf_text(job.link)
        elif low.endswith((".xls", ".xlsx")):
            text = _excel_text(job.link)
        else:
            return
    except Exception as e:
        log(f"[附件] {job.link} 解析失败: {e}")
        return
    if not text:
        return
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
        m = re.search(r"([\u4e00-\u9fa5]{2,20}局|[\u4e00-\u9fa5]{2,20}中心|[\u4e00-\u9fa5]{2,20}医院|[\u4e00-\u9fa5]{2,20}委员会)", text)
        if m:
            job.unit = m.group(1)


# ============ 统一入口 ============
FETCHERS = [
    ("国考", _fetch_guokao),
    ("甘肃组工网", _fetch_gszg),
    ("甘肃省人社厅", _fetch_gansu_hr),
    ("西安人事考试网", _fetch_xapta),
    ("陕西省人社厅", _fetch_shaanxi),
    ("中国公共招聘网", _fetch_mohrss),
    ("事业单位招聘网", _fetch_shiyebian),
    ("高校人才网", _fetch_gaoxiaojob),
]


def run_all():
    jobs = []
    for name, fn in FETCHERS:
        try:
            got = fn()
            jobs.extend(got)
            log(f"[{name}] 解析到 {len(got)} 条")
        except Exception as e:
            log(f"[{name}] 解析器异常: {e}")
    log(f"合计抓取 {len(jobs)} 条公告")
    return jobs

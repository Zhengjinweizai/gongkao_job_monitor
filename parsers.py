"""全部招聘公告解析器：列表抓取 + 统一入口"""
import datetime
import random
import re
import time
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from config import SOURCES
from details import fetch_detail, parse_attachments, try_extract_attachment  # noqa: F401
from http_client import (  # noqa: F401
    USER_AGENTS,
    browser_headers,
    force_ipv4,
    get_session,
    http_download,
    http_get,
    http_post,
)
from models import Job
from utils import log, safe_url


def polite_delay():
    time.sleep(random.uniform(1.0, 3.0))


ANNO_KEYWORDS = ["招聘", "招录", "考录", "选调", "遴选", "聘用",
                 "招募", "补充公告", "拟录用", "公示", "公告"]

NEGATIVE_KEYWORDS = ["大赛", "吉祥物", "征集", "评选", "表彰", "奖项", "奖牌",
                     "比赛", "竞赛", "预算", "决算", "采购", "中标", "成交",
                     "讲座", "培训会", "活动", "征文", "招募令", "志愿者",
                     "成果奖", "审查结果", "课题", "评估", "普查", "任前公示",
                     "拟录用", "拟聘用", "拟录取", "体检", "录取", "录用名单",
                     "结果查询", "结果公示", "成绩查询", "分数线", "资格复审",
                     "面试通知", "进入体检", "考察公告", "考察通知", "递补"]

SKIP_HREF_PREFIXES = ("#", "javascript:", "mailto:", "data:", "tel:")
SKIP_SUFFIXES = (".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".ico",
                 ".svg", ".webp", ".woff", ".woff2")


def extract_announcements_md(md, base_url, keep_words=None, limit=60):
    """解析 r.jina.ai 等 Reader 返回的 markdown 链接（[标题](url)）"""
    keep_words = keep_words or ANNO_KEYWORDS
    seen, items = set(), []
    for m in re.finditer(r"\[([^\]\n]{8,120})\]\((https?://[^)\s]+)\)", md or ""):
        text = m.group(1).strip()
        link = safe_url(m.group(2).strip())
        if not link:
            continue
        if any(k in text for k in NEGATIVE_KEYWORDS):
            continue
        if not any(k in text for k in keep_words):
            continue
        if link in seen:
            continue
        seen.add(link)
        items.append({"title": text, "link": link})
        if len(items) >= limit:
            break
    return items


def extract_announcements(html, base_url, keep_words=None, limit=60):
    if not html:
        return []
    if "<a " not in html and "](" in html:
        return extract_announcements_md(html, base_url, keep_words, limit)
    keep_words = keep_words or ANNO_KEYWORDS
    soup = BeautifulSoup(html, "lxml")
    seen, items = set(), []
    for a in soup.find_all("a", href=True):
        text = (a.get_text() or "").strip().replace("\n", "").replace("\u3000", " ").strip()
        href = (a.get("href") or "").strip()
        if not href or len(text) < 8 or len(text) > 120:
            continue
        low = href.lower()
        if low.startswith(SKIP_HREF_PREFIXES):
            continue
        path = urlsplit(href).path.lower()
        if path.endswith(SKIP_SUFFIXES):
            continue
        if any(k in text for k in NEGATIVE_KEYWORDS):
            continue
        if not any(k in text for k in keep_words):
            continue
        link = safe_url(urljoin(base_url, href))
        if not link or link in seen:
            continue
        seen.add(link)
        items.append({"title": text, "link": link})
        if len(items) >= limit:
            break
    return items


def extract_date(text):
    text = text or ""
    m = re.search(r"(20\d{2})\s*[年./\-]\s*(\d{1,2})\s*[月./\-]\s*(\d{1,2})\s*[日号]?", text)
    if not m:
        return ""
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
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
        raise
    return jobs


# ============ 2. 甘肃组工网（省考/选调） ============
def _fetch_gszg():
    jobs = []
    seen = set()
    failures = []
    base = SOURCES["gszg"]["url"].rstrip("/")
    for url in (base, base + "/gwy/"):
        try:
            html = http_get(url).text
            for it in extract_announcements(html, url):
                link = it["link"]
                if link in seen:
                    continue
                seen.add(link)
                jobs.append(Job(title=it["title"], unit="甘肃组工网", link=link,
                                source="甘肃组工网", publish_date=extract_date(it["title"])))
            polite_delay()
        except Exception as e:
            failures.append(e)
            log(f"[甘肃组工网] {url} 抓取失败: {e}")
    if len(failures) == 2:
        raise RuntimeError(f"all gszg urls failed: {failures[-1]}")
    return jobs


# ============ 3. 甘肃省人社厅 ============
def _fetch_gansu_hr():
    base = SOURCES["gansu_hr"]["url"].rstrip("/")
    urls = [base, base + "/rst/"]
    jobs = []
    loaded = False
    last_error = None
    for url in urls:
        try:
            html = http_get(url).text
            loaded = True
            items = extract_announcements(html, url)
            if items:
                jobs = [Job(title=it["title"], unit="甘肃省人社厅", link=it["link"],
                            source="甘肃省人社厅", publish_date=extract_date(it["title"]))
                        for it in items]
                break
        except Exception as e:
            last_error = e
            log(f"[甘肃省人社厅] {url} 抓取失败: {e}")
        polite_delay()
    if not loaded and last_error is not None:
        raise RuntimeError(f"all gansu_hr urls failed: {last_error}")
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
    browser = None
    try:
        from http_client import fetch_proxy
        with sync_playwright() as p:
            launch_kwargs = {"headless": True}
            proxy = fetch_proxy()
            if proxy:
                launch_kwargs["proxy"] = {"server": proxy}
            browser = p.chromium.launch(**launch_kwargs)
            page = browser.new_page(user_agent=random.choice(USER_AGENTS))
            page.goto(url, timeout=30000)
            page.wait_for_timeout(3000)
            html = page.content()
        items = extract_announcements(html, url)
        return [_to_job(it, "西安人事考试网") for it in items]
    except Exception as e:
        log(f"[西安人事考试网] playwright 抓取失败: {e}")
        return []
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass


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
        raise
    return jobs


# ============ 6. 中国公共招聘网（人社部官方，JSON 接口优先） ============
MOHRSS_API = "https://job.mohrss.gov.cn/cjobs/institution/getinstitutionbyajax"


def _iter_mohrss_items(payload):
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("data", "rows", "list", "result", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
            if isinstance(value, dict):
                for nested in ("list", "rows", "records"):
                    if isinstance(value.get(nested), list):
                        return [x for x in value[nested] if isinstance(x, dict)]
    return []


def _fetch_mohrss():
    jobs = []
    errors = []
    try:
        h = browser_headers(referer="https://job.mohrss.gov.cn/")
        h["X-Requested-With"] = "XMLHttpRequest"
        r = http_post(MOHRSS_API, data=None, timeout=20, headers=h)
        for item in _iter_mohrss_items(r.json()):
            title = str(item.get("title") or "")
            cid = str(item.get("contentId") or "")
            renshu = str(item.get("renshu") or "")
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
        errors.append(e)
        log(f"[中国公共招聘网] JSON 接口失败: {e}")
    try:
        url = "https://job.mohrss.gov.cn/cjobs/institution/listInstitution?pageNo=1"
        r = http_get(url, timeout=20)
        for it in extract_announcements(r.text, url, limit=60):
            jobs.append(Job(title=it["title"], unit="", link=it["link"],
                            source="中国公共招聘网", publish_date=extract_date(it["title"])))
        polite_delay()
    except Exception as e:
        errors.append(e)
        log(f"[中国公共招聘网] 列表页兜底失败: {e}")
    if not jobs and len(errors) == 2:
        raise RuntimeError(f"mohrss json+list failed: {errors[-1]}")
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
        if en in (path or ""):
            return zh
    return ""


def _combine_md(md, today, title=""):
    """把列表页的 “11-03” 补全为完整日期；完整日期直接复用 extract_date。"""
    md = (md or "").strip()
    full = extract_date(md)
    if full:
        return full
    m = re.search(r"(?<!\d)(\d{1,2})-(\d{1,2})(?!\d)", md)
    if not m:
        return ""
    month, day = int(m.group(1)), int(m.group(2))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return ""
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


def _fetch_shiyebian(today=None):
    today = today or datetime.date.today()
    base = SOURCES["shiyebian"]["url"].rstrip("/")
    jobs = []
    errors = []
    loaded = 0
    for url in (base + "/", base + "/gansu/", base + "/shanxisheng/"):
        try:
            r = http_get(url, encoding="gbk")
            loaded += 1
            if getattr(r, "is_markdown", False):
                for it in extract_announcements(r.text, url, limit=50):
                    title = it["title"]
                    jobs.append(Job(title=title, unit="", link=it["link"],
                                    source="事业单位招聘网",
                                    publish_date=extract_date(title)))
                continue
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
                link = safe_url(urljoin(url, title_a.get("href") or ""))
                if not title or len(title) < 8 or not link:
                    continue
                if any(k in title for k in NEGATIVE_KEYWORDS):
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
            errors.append(e)
            log(f"[事业单位招聘网] 抓取 {url} 失败: {e}")
    if loaded == 0 and errors:
        raise RuntimeError(f"all shiyebian urls failed: {errors[-1]}")
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
    loaded = 0
    errors = []
    sess = get_session()
    try:
        sess.get(SOURCES["gaoxiaojob"]["url"], timeout=20)   # 预热 Cookie
        polite_delay()
    except Exception as e:
        log(f"[高校人才网] 首页预热失败: {e}")
    for url, label in GAOXIAOJOB_PAGES:
        try:
            r = http_get(url, headers=browser_headers(referer="https://www.gaoxiaojob.com/"))
            loaded += 1
            for it in extract_announcements(r.text, url, keep_words=GAOXIAOJOB_KEEP, limit=50):
                link = it["link"]
                if "/announcement/detail/" not in link:
                    continue
                if link in seen:
                    continue
                seen.add(link)
                title = it["title"].split("：", 1)[-1] if "：" in it["title"] else it["title"]
                # label 是列表栏目名，不是招聘单位；放入 category，避免污染专业匹配
                job = Job(title=title, unit="", category=label, link=link,
                          source="高校人才网", publish_date=extract_date(it["title"]))
                if label in ("甘肃", "陕西", "西安", "兰州"):
                    job.location = label
                jobs.append(job)
            polite_delay()
        except Exception as e:
            errors.append(e)
            log(f"[高校人才网] {url} 抓取失败: {e}")
    if loaded == 0 and errors:
        raise RuntimeError(f"all gaoxiaojob pages failed: {errors[-1]}")
    return jobs


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


def run_all(return_report=False):
    """抓取全部数据源；单源失败不阻塞，返回可选的分源健康报告。"""
    force_ipv4()
    jobs = []
    report = []
    for name, fn in FETCHERS:
        try:
            got = fn()
            if got is None:
                raise TypeError("fetcher returned None")
            got = list(got)
            jobs.extend(got)
            report.append({"name": name, "count": len(got), "error": ""})
            log(f"[{name}] 解析到 {len(got)} 条")
        except Exception as e:
            report.append({"name": name, "count": 0, "error": str(e)})
            log(f"[{name}] 解析器异常: {e}")
    healthy = sum(1 for item in report if item["count"] > 0)
    log(f"合计抓取 {len(jobs)} 条公告（{healthy}/{len(report)} 个数据源有结果）")
    if return_report:
        return jobs, report
    return jobs

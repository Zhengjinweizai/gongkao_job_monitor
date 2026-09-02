"""国企/央企轨道数据源抓取（复用 parsers 的 http_get / reader / 既有可靠源抓取器，不改 parsers）

说明：
- 集团官网/国聘多为 JS 系统，海外 runner 直连成功率低 -> 尽力抓，失败自动跳过；
- 兜底：复用事业单位招聘网 / 高校人才网 / 中国公共招聘网 等成熟抓取器拿到的全量公告，
  再经 0-100 评分里的“企业资质>=12”过滤，只保留确含央企/国企/地方国企的岗位。
  单源失败绝不影响整体。
"""
from parsers import http_get, extract_announcements, extract_date, log, polite_delay
from parsers import _reader_fetch
from parsers import _fetch_shiyebian, _fetch_gaoxiaojob

# (key, 展示名, url, keep_words) —— 集团官网/国聘等直连源（尽力而为）
SOE_LISTINGS = [
    ("iguopin", "国聘网", "https://www.iguopin.com/",
     ["招聘", "校招", "校园招聘", "应届", "社招", "岗位"]),
    ("sinopharm", "国药集团", "http://www.sinopharm.com/",
     ["招聘", "校招", "校园招聘", "人才", "引进"]),
    ("cetc", "中国电科", "https://www.cetc.com.cn/",
     ["招聘", "校招", "校园招聘", "人才", "引进"]),
    ("cec", "中国电子", "https://www.cec.com.cn/",
     ["招聘", "校招", "校园招聘", "人才", "引进"]),
    ("cnnc", "中核集团", "http://www.cnnc.com.cn/",
     ["招聘", "校招", "校园招聘", "人才", "引进"]),
    ("genertec", "通用技术集团", "https://www.genertec.com.cn/",
     ["招聘", "校招", "校园招聘", "人才", "引进"]),
]

MAX_PER_PAGE = 40


def _listing(url, keep_words, label, limit=MAX_PER_PAGE):
    """抓一个列表页：直连 HTML 优先，条目为空则强制 reader 渲染（覆盖 SPA / WAF）"""
    items = []
    try:
        r = http_get(url, timeout=25)
        items = extract_announcements(r.text, url, keep_words=keep_words, limit=limit)
        if items:
            log(f"[soe:{label}] 直连解析 {len(items)} 条")
    except Exception as e:
        log(f"[soe:{label}] 直连失败({type(e).__name__})，尝试 reader")
    if not items:
        try:
            rr = _reader_fetch(url, 35, None)
            if rr is not None:
                items = extract_announcements(rr.text, url, keep_words=keep_words, limit=limit)
                log(f"[soe:{label}] reader 渲染解析 {len(items)} 条")
        except Exception as e:
            log(f"[soe:{label}] reader 兜底失败: {e}")
    polite_delay()
    return items


def _to_rec(title, link, source, unit="", location="", province="", city="",
            education="", major_req="", deadline="", publish_date=""):
    return {"title": title, "unit": unit, "location": location,
            "province": province, "city": city, "education": education,
            "major_req": major_req, "deadline": deadline, "link": link,
            "source": source, "publish_date": publish_date}


def _direct_sources():
    records = []
    for key, label, url, keep in SOE_LISTINGS:
        try:
            for it in _listing(url, keep, label):
                records.append(_to_rec(it["title"], it["link"], label,
                                       publish_date=extract_date(it["title"])))
            log(f"[soe:{label}] 汇总 {len(records)} 条")
        except Exception as e:
            log(f"[soe:{label}] 解析器异常: {e}")
    return records


def _reuse_aggregators():
    """复用成熟聚合源抓取器拿全量公告，交评分层做央企/国企过滤"""
    out = []
    fetchers = [("事业单位招聘网", _fetch_shiyebian), ("高校人才网", _fetch_gaoxiaojob)]
    for label, fn in fetchers:
        try:
            jobs = fn()
            for j in jobs:
                out.append(_to_rec(j.title, j.link, label, unit=j.unit,
                                   location=j.location, province=j.province,
                                   city=j.city, education=j.education,
                                   major_req=j.major_req, deadline=j.deadline,
                                   publish_date=j.publish_date))
            log(f"[soe:复用-{label}] 取得 {len(jobs)} 条待筛")
        except Exception as e:
            log(f"[soe:复用-{label}] 失败: {e}")
    return out


def run_all():
    records, seen = [], set()
    for batch in (_direct_sources(), _reuse_aggregators()):
        for rec in batch:
            if rec["link"] in seen:
                continue
            seen.add(rec["link"])
            records.append(rec)
    log(f"[soe] 合计抓取 {len(records)} 条候选（含聚合站全量，待评分过滤）")
    return records

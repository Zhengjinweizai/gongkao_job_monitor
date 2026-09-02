"""考公岗位智能匹配监控 - 配置文件"""
import os

# ============ 地域权重（严格按用户规则）============
REGION_HIGH = 3    # 天水市 / 西安市
REGION_MED = 1     # 甘肃省(除天水) / 陕西省(除西安)
REGION_LOW = 0     # 全国其他省份（专业匹配仍保留并推送）

GANSUN = "甘肃"
SHAANXI = "陕西"

# ============ 专业匹配关键词 ============
# 强匹配（+5）
STRONG_MAJOR_KEYWORDS = [
    "生物医学", "生物工程", "生物技术", "生物科学", "生物医药",
    "医学", "临床医学", "基础医学", "公共卫生", "预防医学",
    "药学", "生命科学", "卫生检验", "医疗器械", "医保",
    "医药", "卫生", "医学检验",
]
# 通用匹配（+2）
GENERAL_MAJOR_KEYWORDS = [
    "专业不限", "不限专业", "管理类", "综合类",
    "文学类", "法学类", "哲学类", "经济学类", "公共管理",
]

# ============ 时效参数 ============
VALID_WINDOW_DAYS = 30      # 无明确截止日期的公告，默认按发布日期+30天推定有效
EXPIRE_SOON_DAYS = 3        # 截止前 3 天标记"即将截止"
EXPIRE_PURGE_DAYS = 1       # 过期超过该天数后从历史记录自动删除（宽限期，防止误删截止当天仍可报岗位）
GRADUATE_DATE = "2027-06"   # 你的毕业时间（应届生身份时效锚点）

# ============ 推送阈值 ============
PUSH_MIN_SCORE = 2          # 只推送匹配度 >= 2 的当天新岗位

# ============ 岗位类型分档（公务员 > 事业编制 > 其他）============
# 用于推送与历史记录的排序置顶（tier: 1=公务员 2=事业编制 3=其他）
CIVIL_SERVER_SOURCES = {"国家公务员局", "甘肃组工网"}
CIVIL_SERVER_KEYWORDS = ["公务员", "选调", "遴选", "补充录用", "省考", "国考", "考录"]
PUBLIC_INST_SOURCES = {"中国公共招聘网", "甘肃省人社厅", "陕西省人社厅",
                       "西安人事考试网", "事业单位招聘网"}
PUBLIC_INST_KEYWORDS = ["事业编", "编制", "入编", "纳编", "公开招聘", "人才引进",
                        "引进", "三支一扶", "特岗", "教师招聘"]
PUBLIC_INST_UNIT_KEYWORDS = ["医院", "卫生院", "疾控", "卫健委", "中小学", "高校",
                             "大学", "学院", "研究院", "学校", "中心"]
NON_ESTABLISHMENT_KEYWORDS = ["劳务派遣", "派遣制", "编外", "员额", "外包",
                              "政府购买", "合同制", "临聘", "聘用制",
                              "科研助理", "博士后"]

# ============ 数据源 ============
SOURCES = {
    "guokao":   {"name": "国家公务员局",   "url": "http://www.scs.gov.cn"},
    "gszg":     {"name": "甘肃组工网",     "url": "http://www.gszg.gov.cn"},
    "gansu_hr": {"name": "甘肃省人社厅",   "url": "http://rst.gansu.gov.cn"},
    "xapta":    {"name": "西安人事考试网", "url": "https://xapta.xa.gov.cn"},
    "shaanxi":  {"name": "陕西省人社厅",   "url": "http://rst.shaanxi.gov.cn"},
    "mohrss":   {"name": "中国公共招聘网", "url": "https://job.mohrss.gov.cn"},
    "shiyebian": {"name": "事业单位招聘网", "url": "https://www.shiyebian.net"},
    "gaoxiaojob": {"name": "高校人才网", "url": "https://www.gaoxiaojob.com"},
}

# 附件解析开关
PARSE_ATTACHMENT = True     # 对 Excel/PDF 附件尝试提取文字（pandas / pypdf）

# ============ 环境变量（GitHub Secrets / Vars 注入）============
SERVER_CHAN_KEY = os.getenv("SERVER_CHAN_KEY", "")
PAGES_URL = os.getenv("PAGES_URL", "")

# ============ 文件路径 ============
HISTORY_FILE = "history.json"
HTML_FILE = "site/history.html"     # 输出到 site/ 子目录，供 GitHub Pages 官方部署上传

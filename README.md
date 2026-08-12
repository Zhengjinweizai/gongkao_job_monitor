# gongkao-job-monitor

每日自动抓取全国公务员/事业单位招聘公告，按"生物医学硕士 · 2027届应届 · 天水生源"身份智能匹配打分，微信（Server酱）推送重点岗位，并自动生成可视化历史记录页（可部署到 GitHub Pages）。

## 功能特性

- **全国多源覆盖**：甘肃组工网、甘肃省人社厅、西安人事考试网、陕西省人社厅、国家公务员局（国考）、**中国公共招聘网（人社部官方 JSON 接口）**、**事业单位招聘网（GBK 聚合源，覆盖全国各省）**、**高校人才网（高校/中小学校/医卫院校等事业单位范畴）**
- **智能匹配打分**：地域权重（天水/西安 +3、甘陕其他 +1、外省 +0）+ 专业匹配（生物医学类 +5、通用类 +2），外省高匹配岗位同样纳入搜索与推送
- **只推招聘公告**：自动滤除"体检公告 / 录取公告 / 拟录用公示 / 成绩查询"等结果与流程类公告
- **时效过滤**：已过报名截止的岗位不推送；截止前 3 天标记"⚠️ 即将截止"；无截止日期的按发布日期 + 30 天推定有效；**过期超过 1 天自动从历史记录删除**（宽限期 1 天，避免误删截止当天仍可报岗位）
- **微信推送**：只推送当天新增且匹配度 ≥ 2 的岗位；无新增则推送"静默消息"；**支持双微信号**（两个 Server酱 账号各推一次）
- **历史可视化**：自动生成 `history.html`（蓝白风格、移动端适配），分为 **① 每日新增（可显示"今日无新增"）** 和 **② 历史累计岗位** 两部分，推送 GitHub Pages + Actions Artifact
- **去重**：以 `单位+岗位+发布日期+链接` 的 MD5 为唯一标识存入 `history.json`，跨天运行不重复推送
- **健壮性**：单源失败自动跳过；随机 UA + 1~3 秒随机延时；Excel/PDF 附件尝试自动解析

## 目录结构

```
gongkao-job-monitor/
├── .github/workflows/monitor.yml   # 每日 8:00 / 20:00（北京时间）+ 手动触发
├── main.py                         # 主流程
├── config.py                       # 权重、关键词、数据源、时效/薪资/备考参数
├── parsers.py                      # 全部站点解析器（合一）+ 附件解析
├── filters.py                      # 地域加权 + 专业打分 + 时效判断 + 备考/薪酬生成
├── notifier.py                     # Server酱（Turbo）推送
├── storage.py                      # history.json 读写与去重
├── generate_html.py                # 生成 history.html
├── requirements.txt
└── README.md
```

## 匹配打分规则

| 维度 | 规则 | 分数 |
|---|---|---|
| 地域 | 工作地点 = 天水市 或 西安市 | +3 |
| 地域 | 甘肃省（除天水）或 陕西省（除西安） | +1 |
| 地域 | 全国其他省份（专业匹配仍保留并推送） | +0 |
| 专业 | 含 生物医学/生物工程/医学/临床/公共卫生/预防医学/药学/生命科学/卫生检验/医疗器械/医保 等 | +5 |
| 专业 | 专业不限 / 管理类 / 综合类 / 文学类 / 法学类 等 | +2 |

**推送阈值**：匹配度 ≥ 2 且当天新增、未过报名截止。

## 部署步骤

### 1. 上传代码到 GitHub

```bash
git init
git add .
git commit -m "init"
git branch -M main
git remote add origin https://github.com/<你的用户名>/gongkao-job-monitor.git
git push -u origin main
```

### 2. 配置 Secrets / Variables

仓库 `Settings → Secrets and variables → Actions`：

| 类型 | 名称 | 说明 |
|---|---|---|
| **Secret** | `SERVER_CHAN_KEY` | 微信① 的 Server酱 Turbo SendKey（`sct.ftqq.com` 获取） |
| **Secret** | `SERVER_CHAN_KEY_2` | 微信② 的 SendKey（可选，两个微信号各绑一个 Server酱 账号） |
| **Variable** | `PAGES_URL` | 可选，GitHub Pages 地址，如 `https://<用户名>.github.io/gongkao-job-monitor/history.html` |

> `GITHUB_TOKEN` 由 GitHub 自动提供，无需手动配置。

**双微信号推送设置**：
1. 用微信① 注册/登录 Server酱（`sct.ftqq.com`）→ 复制 SendKey → 填入 `SERVER_CHAN_KEY`；
2. 用微信② **重新注册一个 Server酱 账号**（`sct.ftqq.com`）→ 复制 SendKey → 填入 `SERVER_CHAN_KEY_2`；
3. 两个微信会各收到一次相同内容的推送。若日后还想加第三个号，继续新增 `SERVER_CHAN_KEY_3` Secret 即可（脚本自动识别所有 `SERVER_CHAN_KEY*`）。

### 3. 开启 GitHub Pages

1. 仓库 `Settings → Pages`
2. Build and deployment → Source 选择 **Deploy from a branch**
3. Branch 选 **`gh-pages`** → 保存
4. 首次 Actions 运行成功后，访问 `https://<用户名>.github.io/gongkao-job-monitor/history.html`

### 4. 手动触发一次

仓库 `Actions → gongkao-job-monitor → Run workflow`（绿色按钮），确认第一次运行成功、`history.html` 生成并部署。

## 查看历史记录

- **在线预览**：开启 Pages 后访问上面的 URL
- **Actions Artifact**：每次运行结束后，`Actions → 本次运行 → Artifacts → history-page` 下载 `history.html`

## 本地运行（可选）

```bash
pip install -r requirements.txt
python -m playwright install chromium   # 西安站 JS 渲染兜底用
set SERVER_CHAN_KEY=你的SendKey          # Windows
export SERVER_CHAN_KEY=你的SendKey      # Linux / macOS
python main.py
```

> 未配置 `SERVER_CHAN_KEY` 时会跳过微信推送，但照常生成 `history.html` 与 `history.json`。

## 自定义

- **修改关键词 / 权重 / 时效参数 / 薪酬参考**：编辑 `config.py`
- **修改推送文案**：编辑 `notifier.py`
- **修改历史页样式**：编辑 `generate_html.py`
- **增删数据源**：在 `config.py` 的 `SOURCES` 增删，并在 `parsers.py` 的 `FETCHERS` 注册对应函数

## 免责声明

本工具仅作个人备考信息聚合，抓取频率低（每日 2 次），请遵守目标网站的 robots 与访问规范。所有岗位信息以各官方发布公告为准，本工具不构成报考建议。

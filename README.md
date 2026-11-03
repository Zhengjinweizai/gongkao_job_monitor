# 考公推送

每日自动抓取全国公务员/事业单位招聘公告，按“生物医学硕士 · 2027 届应届 · 天水生源”身份智能匹配打分，微信（Server酱）推送重点岗位，并自动生成可部署到 GitHub Pages 的可视化历史记录页。

## 功能特性

- **全国多源覆盖**：甘肃组工网、甘肃省人社厅、西安人事考试网、陕西省人社厅、国家公务员局（国考）、中国公共招聘网（人社部 JSON 接口）、事业单位招聘网（GBK 聚合源）、高校人才网。
- **智能匹配打分**：地域权重（天水/西安 +3、甘陕其他 +1、外省 +0）+ 专业匹配（生物医学类 +5、通用类 +2）。只对**标题 + 岗位专业要求**打分，列表栏目名（如“医学人才”）不再污染专业匹配。
- **只推招聘公告**：自动滤除体检、录取、拟录用公示、成绩查询等结果/流程类公告。
- **时效过滤**：已过报名截止的岗位不推送；截止前 3 天标记“⚠️ 即将截止”；无截止日期的按**发布日期 / 首次发现日期 + 30 天**推定有效；过期超过 1 天从历史记录删除（宽限期 1 天）。
- **稳定去重**：以**规范化 URL + 标题年份**（忽略协议大小写、末尾斜杠、`utm_*` 等跟踪参数）作为唯一标识；同一 URL 跨年度复用会保留新记录，首次升级会自动合并同一 URL/年份的重复链接。
- **微信推送**：只推送当天新增且匹配度 ≥ 2 的岗位；无新增则推送“静默消息”；支持多个 Server酱 账号（`SERVER_CHAN_KEY`、`SERVER_CHAN_KEY_2`…）。**校验 Server酱 业务码**，配额耗尽/密钥失效会明确记录，不再静默成功。
- **历史可视化**：自动生成 `site/history.html`（蓝白风格、移动端适配），分为 ① 每日新增 ② 历史累计，并内联展开匹配说明/薪资/条件/政审/备考。
- **附件解析**：详情页里的岗位表 PDF / Excel（`.xlsx` 用 openpyxl，`.xls` 用 xlrd）会尝试下载并提取专业、学历、单位等文本。
- **健壮性**：单源失败自动跳过；随机 UA + 1~3 秒随机延时；统一 HTTP 层（忽略坏代理、连接错误/5xx/408/429 自动重试、403/412 走 Reader 兜底）；每次运行输出**分数据源健康度**，全部数据源无结果时推送告警。
- **历史安全**：`history.json` 原子写入（临时文件 + fsync + replace）；每次保存前把上一份可解析的主文件备份为 `history.json.bak`，主文件损坏/缺失时自动回退备份，不静默清空历史。

## 目录结构

```
考公推送/
├── .github/
│   ├── workflows/monitor.yml   # 每日 00:00（北京时间）抓取 + 提交历史 + Pages 部署
│   ├── workflows/ci.yml        # ruff + pytest + pip-audit
│   └── dependabot.yml          # 依赖与 Actions 每周更新
├── main.py                     # 主流程：迁移/去重 → 抓取 → 打分 → 详情 → 推送 → HTML
├── config.py                   # 权重、关键词、数据源、时效/预算参数
├── models.py                   # Job 数据模型 + 规范化 URL 唯一 ID
├── filters.py                  # 地域加权 + 专业打分 + 时效判断 + 备考/薪酬生成
├── http_client.py              # 统一 HTTP 层（重试 / Reader 兜底 / 代理）
├── parsers.py                  # 8 个列表页抓取器 + 列表/日期解析
├── details.py                  # 详情页字段提取 + PDF/Excel 附件解析
├── notifier.py                 # Server酱 推送与消息组装
├── storage.py                  # history.json 原子读写、备份、去重
├── generate_html.py            # 生成 site/history.html 与 index.html
├── utils.py                    # 日志、URL 规范化、URL 白名单、原子写入
├── tests/                      # pytest 测试套件（离线，不访问真实站点）
├── requirements.txt            # 运行时依赖（精确版本）
├── requirements-dev.txt        # 测试/静态检查/审计依赖
├── pyproject.toml              # pytest / coverage / ruff 配置
└── README.md
```

## 匹配打分规则

| 维度 | 规则 | 分数 |
|---|---|---|
| 地域 | 工作地点 = 天水市 或 西安市 | +3 |
| 地域 | 甘肃省（除天水）或 陕西省（除西安） | +1 |
| 地域 | 全国其他省份（专业匹配仍保留并推送） | +0 |
| 专业 | 标题/专业要求含 生物医学/生物工程/医学/临床/公共卫生/预防医学/药学/生命科学/卫生检验/医疗器械/医保 等 | +5 |
| 专业 | 专业不限 / 管理类 / 综合类 / 文学类 / 法学类 等 | +2 |

**推送阈值**：匹配度 ≥ 2 且当天新增、未过报名截止。

## 运行时间

- GitHub Actions 定时：`cron: "0 16 * * *"`，即**北京时间每天 00:00** 运行一次。
- 工作流设置 `TZ=Asia/Shanghai`，代码也按 `config.TIMEZONE` 计算“今日”，避免 UTC 跨日导致每日新增错位。
- 支持 `workflow_dispatch` 手动触发；手动运行只在 `main` 分支执行，避免把分支代码/历史推到 `main`。

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
| **Secret** | `SERVER_CHAN_KEY_3` | 微信③ 的 SendKey（可选；更多账号需在 `monitor.yml` 继续增加 env 条目） |
| **Variable** | `PAGES_URL` | 可选，GitHub Pages 地址，如 `https://<用户名>.github.io/gongkao-job-monitor/history.html`；不填则根据 `GITHUB_REPOSITORY` 自动推导 |
| **Secret/Variable** | `FETCH_PROXY` | 可选，HTTP(S) 代理地址；含账号口令时请存为 Secret |
| **Secret/Variable** | `READER_PROXY` | 可选，直连失败时的兜底抓取服务，默认 `https://r.jina.ai/`；留空也会使用默认值 |

> `GITHUB_TOKEN` 由 GitHub 自动提供，无需手动配置。

**双微信号推送设置**：

1. 用微信① 注册/登录 Server酱（`sct.ftqq.com`）→ 复制 SendKey → 填入 `SERVER_CHAN_KEY`；
2. 用微信② **重新注册一个 Server酱 账号** → 复制 SendKey → 填入 `SERVER_CHAN_KEY_2`；
3. 两个微信会各收到一次相同内容的推送。工作流已注入 `SERVER_CHAN_KEY_3`；若日后还想加第四个号，在 `monitor.yml` 的 `env` 中增加 `SERVER_CHAN_KEY_4` 并绑定同名 Secret（脚本自动识别 `SERVER_CHAN_KEY` / `SERVER_CHAN_KEY_<数字>`）。

### 3. 开启 GitHub Pages（官方 Actions 部署方式）

1. 仓库 `Settings → Pages`；
2. Build and deployment → Source 选择 **`GitHub Actions`**（不是 “Deploy from a branch”）→ 保存；
3. 触发一次 Actions（`Actions → Run workflow`），首次运行成功后：
   - 页面 URL 为 `https://<用户名>.github.io/<仓库名>/history.html`
   - 例如：`https://Zhengjinweizai.github.io/gongkao_job_monitor/history.html`

工作流已拆分为 `monitor`（抓取 + 提交 `history.json` + 上传 `site/` artifact）和 `deploy`（Pages 部署）两个 job；部署使用独立的 `pages` 并发组且不取消进行中的部署。

> `main` 分支需允许 GitHub Actions 直接推送（或为 `github-actions[bot]` 配置规则集绕过）；若开启了“必须通过 PR / 必须签名提交”，机器人提交会被拒绝，需要调整分支保护。

> Pages 的 Source 必须选择 **GitHub Actions**，否则 `configure-pages` / `deploy-pages` 会在首次运行时报 “Get Pages site failed”。

### 4. 手动触发一次

仓库 `Actions → gongkao-job-monitor → Run workflow`（绿色按钮），确认第一次运行成功、`history.html` 生成并部署。

## 查看历史记录

- **在线预览**：开启 Pages 后访问上面的 URL。
- **Actions Artifact**：每次运行结束后，`Actions → 本次运行 → Artifacts → history-site` 下载 `history.html` / `index.html`。

## 本地运行（可选）

```bash
pip install -r requirements.txt
python -m playwright install chromium   # 西安站 JS 渲染兜底用，可选
export SERVER_CHAN_KEY=你的SendKey      # Linux / macOS；Windows 用 set
python main.py
```

未配置 `SERVER_CHAN_KEY` 时会跳过微信推送，但照常生成 `history.html` 与 `history.json`。

## 测试与质量检查

```bash
pip install -r requirements-dev.txt
ruff check .
python -m pytest --cov --cov-branch --cov-report=term-missing
pip-audit -r requirements.txt --strict
```

- 测试全部离线：网络调用在 `tests/conftest.py` 中被禁用，抓取器通过 fake `http_get` / `http_post` / fake session 覆盖。
- CI（`.github/workflows/ci.yml`）在 push / PR / 每周一定时运行 ruff、pytest（覆盖率门槛 85%）和 pip-audit。
- 依赖使用精确版本；Dependabot 每周更新 pip 与 GitHub Actions；Actions 固定到完整 commit SHA。

## 数据迁移说明

从旧版本升级后的第一次运行会：

1. 把 `unique_id` 从 `单位|标题|发布日期|链接` 切换为**规范化 URL + 标题年份**（同一 URL 跨年度复用时仍视为两条记录）；
2. 合并同一 URL/年份的重复记录（当前仓库 2026-11 数据实测 888 条 → 约 630 条），保留最近观测到的一条并补齐空字段；
3. 把高校人才网的栏目名（如“医学人才”）从 `unit` 移到 `category`，不再参与专业 +5；
4. 对没有发布日期的旧记录使用 `fetched_at`/首次发现日期作为 30 天时效锚点，因此一批很久以前的历史岗位会按既有规则过期并清理（同一份 2026-11 数据实测：去重后约 630 条，按 30 天规则清理后约 180 条，其中多数为无明确截止日期的推定过期）。

`history.json` 采用原子写入；`history.json.bak` 保存的是**上一份可解析的主文件**，首次迁移前还会写入 `history.json.pre-migration-<日期>` 快照。两者都不提交到仓库，CI 环境中的最终恢复路径仍是 Git 历史中的上一版 `history.json`。

## 自定义

- **修改关键词 / 权重 / 时效参数 / 运行预算**：编辑 `config.py`
- **修改推送文案**：编辑 `notifier.py`
- **修改历史页样式**：编辑 `generate_html.py`
- **增删数据源**：在 `config.py` 的 `SOURCES` 增删，并在 `parsers.py` 的 `FETCHERS` 注册对应函数

## 免责声明

本工具仅作个人备考信息聚合，抓取频率低（每日 1 次），请遵守目标网站的 robots 与访问规范。所有岗位信息以各官方发布公告为准，本工具不构成报考建议。

## 海外部署网络方案（GitHub Actions）

GitHub Actions 运行器位于美国，部分国内站点会因海外 IP / WAF 反爬导致抓取失败。本项目通过三层机制解决：

1. **忽略系统/环境代理**：HTTP 层统一 `trust_env=False`，不会因本地/共享坏代理产生 `ProxyError`；只有显式设置 `FETCH_PROXY` 时才走代理。
2. **自动重试**：连接错误、超时、5xx、408、429 自动指数退避重试（最多 3 次，429 尊重 `Retry-After`）；403/412 反爬不浪费时间重试，直接进入兜底。
3. **Reader 兜底**：直连被 WAF 或海外 IP 拦截时，自动改经 `READER_PROXY`（默认 `https://r.jina.ai/`）获取公告列表/详情，并解析其 markdown 链接；Reader 返回 UTF-8 markdown，不会套用原站 GBK 编码。

实测各源表现（历史记录，供参考）：

| 数据源 | 海外/反爬表现 | 处理 |
|---|---|---|
| 事业单位招聘网 | 稳定 | 直接抓取（GBK） |
| 高校人才网 | Cookie 预热 + 偶尔超时 | 自动重试 + reader 兜底 |
| 甘肃组工网 | 栏目 `/tzgg /rsks /sydw` 已 404（已移除） | 首页 + `/gwy/`，reader 兜底 |
| 甘肃省人社厅 | WAF 反爬 412（直连必败） | **reader 兜底正常绕过** |
| 国家公务员局 | 海外稳定 | 直接抓取 |
| 陕西省人社厅 | 少数时段无数据 | 直接抓取 |
| 西安人事考试网 | TLS 握手失败，jina 亦 422 | 视为弱源，JS 渲染兜底 |
| 中国公共招聘网 | JSON/TLS 不通，jina 422 | 视为弱源，JSON→列表双兜底 |

> 若某源在贵网络始终不可用，可在 GitHub Actions 设置 `FETCH_PROXY`（国内代理）替它直连。日常信息以聚合站（事业单位招聘网、高校人才网）为主，官方 gov 站为辅。

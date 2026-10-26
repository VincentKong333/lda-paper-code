# 广州市民诉求数据采集与分析 · liuyan-scraper

人民网「领导留言板」广州市 13 个板块的公开留言采集、文本主题建模（LDA）与政府回应时延分析（生存分析）。

> 数据窗口 **2024-10-01 ~ 2026-08-31**（23 个完整自然月）· **10,182 条** · 22 字段 · 统一快照

---

## 目录

- [1. 项目概览](#1-项目概览)
- [2. 仓库结构](#2-仓库结构)
- [3. 快速开始](#3-快速开始)
- [4. 七步流程](#4-七步流程)
- [5. 数据说明](#5-数据说明)
- [6. 字段字典](#6-字段字典)
- [7. 主要结果](#7-主要结果)
- [8. 合规与伦理](#8-合规与伦理)
- [9. 平台差异](#9-平台差异)
- [10. 变更记录](#10-变更记录)

---

## 1. 项目概览

| 项 | 值 |
|---|---|
| 数据源 | 人民网「领导留言板」PC 端公开接口（无需登录） |
| 采集范围 | 广州市 2 个市级板块（市委书记、市长）+ 11 个区级板块 |
| 数据量 | 10,182 条（tid 全表唯一，零重复） |
| 时间窗 | 2024-10-01 ~ 2026-08-31，23 个完整自然月 |
| 采集耗时 | 17.5 小时，全程零限流 |
| 主分析 | LDA 主题建模（K=6，UMass 一致性选型） |
| 辅助分析 | Kaplan-Meier + log-rank + Cox（lifelines） |

**核心设计**：不模拟浏览器。站点虽为 SPA，但数据由 XHR 以 JSON 下发，直接调用列表接口
（`/v1/threads/list/df` 取 tid）与详情接口（`/v1/threads/content` 取正文与回复），
请求签名 `md5(路径 + 紧凑JSON(param) + SECRET + token)`。

---

## 2. 仓库结构

```
liuyan-scraper/
├── config.py                 # ★唯一配置源：板块、时间窗、节奏、输出名
├── scraper_collect.py        # ★采集主脚本：列表翻页 → 详情 → 22 字段 jsonl
├── check_env.py              # 换机自检（6 项，仅发 2 个真实请求）
├── probe_window.py           # 可采范围探测（只读，带总时长安全阀）
├── preflight_window.py       # 零网络预检（改窗口后先算命中条数）
├── content_lda.py            # ★LDA 主分析
├── survival_cox.py           # ★生存分析（KM / log-rank / Cox）
├── export_excel.py           # jsonl → 全字段 Excel
├── run_scraper_win.py        # Windows 长跑启动器（防休眠 + PID + UTF-8）
├── start.sh / stop.sh        # macOS/Linux 启停（caffeinate 防休眠）
├── stopwords.txt             # 停用词表（3 轮实测迭代）
├── userdict.txt              # jieba 自定义词典
├── checksums.sha256          # 原始数据指纹（文件本身不入库）
├── tools/                    # 辅助与诊断脚本（10 个，含 verify_dataset.py 核验器）
├── legacy/                   # 历史废弃路线（6 个，勿用于新流程）
├── docs/                     # 交接手册、复现手册、核验说明、论文草稿、Word 报告
├── results/                  # 分析产物（报告 / 图 / 汇总表，无正文）
└── logs/                     # 运行日志（不入库）
```

**分档原则**：根目录只放全流程必需脚本；`tools/` 是排障用的单点工具；
`legacy/` 是已被替代的方案，保留仅为考古与对照。

---

## 3. 快速开始

```bash
# 环境（采集侧零依赖，分析侧 6 个包）
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 采集前必须设置签名密钥（仓库不提供该值，未设置时脚本会直接报错）
export LIUYAN_SECRET=<密钥>        # Windows PowerShell: $env:LIUYAN_SECRET="<密钥>"

# 自检（发 2 个真实请求，验证签名与接口可用）
python3 check_env.py
```

> 只跑分析（LDA / 生存分析 / 导出）时**不需要** `LIUYAN_SECRET`，只有采集与探测类脚本需要。

macOS/Linux 直接 `./start.sh` 采集；Windows 用 `python run_scraper_win.py`。

---

## 4. 七步流程

| 步骤 | 命令 | 耗时 | 通过标准 |
|---|---|---|---|
| S0 环境 | `python3 check_env.py` | 10 s | 6/6 通过 |
| S1 探测 | `python3 probe_window.py` | 16 min | 13 板块最早日期一致 |
| S2 预检 | `python3 preflight_window.py` | 3 s | 窗内条数与预期一致 |
| S3 采集 | `./start.sh` 或 `run_scraper_win.py` | ~17 h | 零 403，条数吻合 |
| S4 质检 | 见 `docs/复现流程手册.md` | 1 min | 零重复、窗外 0、空正文 0 |
| S5 LDA | `python3 content_lda.py --input <jsonl>` | 3~5 min | UMass 曲线有明确最优 |
| S6 生存 | `python3 survival_cox.py --input <jsonl> --censor "<时刻>"` | 20 s | Concordance > 0.7 |
| S7 导出 | `python3 export_excel.py` | 1 min | 行列数与源一致 |

详细命令、参数、坑位见 **[docs/复现流程手册.md](docs/复现流程手册.md)**。

---

## 5. 数据说明

**本仓库不含留言原文。** 这是刻意的隐私处理：正文常含住址、门牌、电话等可反向识别当事人的细节，"公开可访问"不等于"可集中转载"。取舍理由与完整说明见 **[docs/数据可得性与核验说明.md](docs/数据可得性与核验说明.md)**。

| 文件 | 体积 | 入库 | 说明 |
|---|---|---|---|
| `collected_all13_20260914.jsonl` | 18 MB | ❌ | 主数据（含正文），放仓库根目录即可，已被 `.gitignore` 排除 |
| `list_<fid>.json` × 13 | 22 MB | ❌ | 列表缓存，重跑 S1 可重建 |
| `backup_golden_*` | 28 MB | ❌ | 旧数据备份 |
| `results/*.xlsx` | 7 MB | ❌ | 由 `export_excel.py` 随时重建 |
| `results/*.csv`、`*.png`、`*.md` | < 2 MB | ✅ | 只含聚合量与 tid，无正文 |
| `checksums.sha256`、`docs/数据基线.json` | < 10 KB | ✅ | 数据指纹与统计基线 |

**不留原文，但可以自证。** 仓库提供三档核验，逐级加强：

```bash
# ① 指纹：确认是同一份文件
sha256sum -c checksums.sha256

# ② 统计：重算 11 项指标 + 13 板块分布，与基线逐项比对（不读正文）
python tools/verify_dataset.py --input collected_all13_20260914.jsonl

# ③ 复现：数据就位后重跑 analyze / LDA / Cox，核对 results/ 是否一致
```

入库前的原文残留已做过指纹扫描：10,182 条记录的 5 个文本字段取前 12 字为指纹，遍历全部入库文件，命中 **0 处**。

---

## 6. 字段字典

采集输出为 JSON Lines，每行一条留言，共 22 字段。

| 字段 | 含义 |
|---|---|
| `tid` | 留言唯一 ID（主键） |
| `fid` | 板块 ID：1217 市委书记 / 1218 市长 / 2813~2824 区级 |
| `forum_name` | 板块名称 |
| `subject` | 留言标题 |
| `content` | 留言正文全文 |
| `type_name` | 留言类型（建言 / 投诉求助 / 咨询） |
| `domain_name` | 官方领域分类（城建 / 交通 / 环保…） |
| `state_info` | 办理状态 |
| `nick_name` | 用户昵称（平台已脱敏） |
| `from` / `ip_place` | 来源属地 / IP 属地 |
| `create_dateline` / `create_date` | 提交时间戳 / 可读时间 |
| `satisfaction` | 满意度评分 |
| `has_reply` | 1 已回复 / 0 截至快照未回复（生存分析删失标记） |
| `reply_dateline` / `reply_date` | 首次官方回复时间戳 / 时间 |
| `reply_delay_days` | 回复时长（天）= (回复 − 提交) / 86400 |
| `reply_organization` | 回复单位 |
| `reply_nick_name` | 回复人昵称（脱敏） |
| `reply_dept_level` | 回复单位行政层级编码 |
| `reply_content` | 回复正文全文 |

---

## 7. 主要结果

**内容分析（主研究，LDA K=6）**

| 主题 | 占比 | 内容 |
|---|---|---|
| T4 | 23.4% | 道路交通与违停 |
| T2 | 17.0% | 噪音扰民与施工 |
| T0 | 16.9% | 轨道交通与出行 |
| T3 | 15.5% | 房屋质量与维修 |
| T1 | 14.4% | 物业与停车管理 |
| T5 | 12.7% | 摊贩油烟与垃圾 |

层级差异：市级板块 T0 占 28~30%，区级仅 2~17%（宏观建言涌向市级，属地琐事留在区级）。

**回应时延（辅助分析）**

- 总体 KM 中位 **43.0 天**；区级最快从化 13.8 天，市级约 50 天
- 板块 log-rank p<0.001；Cox Concordance **0.745**
- 90 天回复率呈 U 形：2024Q4 89.2% → 2025Q3 67.3% → 2026Q1 75.1%
- 截至快照无回复率 9.9%（1,004 条，按右删失处理）

完整结果见 `results/LDA内容分析报告.md` 与 `results/生存分析报告.md`。

---

## 8. 合规与伦理

- 仅采集**公开页面**数据，不登录、不绕过任何访问控制；
- 请求间隔 4.5~9 秒，每 40 条冷却 30 秒，遇 403 指数退避（30→600 s）；
- 昵称字段已由平台脱敏（`用户77****9`），不含手机号、身份证号、住址等个人信息；
- **原始文本（正文 / 标题 / 昵称 / 回复）不随仓库分发**，仅以聚合统计与数据指纹形式公开；
- 数据仅用于学术研究，论文引用做匿名化处理。

---

## 9. 平台差异

| 能力 | macOS/Linux | Windows |
|---|---|---|
| 启停 | `start.sh` / `stop.sh`（`nohup` + `caffeinate`） | `run_scraper_win.py`（`ctypes` 防休眠 + PID 文件） |
| 依赖 | 采集零依赖 | 同 |
| 编码 | UTF-8 | 需 `PYTHONIOENCODING=utf-8`（启动器已内置） |

`config.py` 的时间戳按东八区计算，两个平台通用，无需修改。

---

## 10. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09 | 首次全量采集：13 板块 10,182 条，统一快照；完成 LDA 与生存分析 |
| 2026-10 | 整理为标准 git 仓库结构；新增复现流程手册与全字段 Excel 导出 |
| 2026-10 | 确立"不含原文"发布原则：新增 `checksums.sha256`、`docs/数据基线.json` 与 `tools/verify_dataset.py`，改为指纹+统计方式核验 |

---

*本项目为本科毕业论文研究材料，数据采集遵循学术伦理与平台使用规范。*

代码以 [Apache-2.0](LICENSE) 协议开源；仓库不含任何留言原文与站点签名密钥。

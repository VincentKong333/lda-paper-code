# 人民网「领导留言板」广州板块爬虫

> ⚠️ **接手请先读 [`爬虫交接文档.md`](爬虫交接文档.md)** —— 里面有完整的部署步骤、原理、配置与排错。

## 一句话说明

直连站点 JSON 接口采集留言数据（**不需要 Selenium，零第三方依赖**），用于「广州市民诉求主题挖掘与政府回应性研究」的学术数据采集。

## 三步开跑

```bash
python3 check_env.py    # 自检（会真实请求接口验证签名）
./start.sh              # 后台启动采集 + 收尾监控
wc -l collected_1217_1218.jsonl   # 看进度
```

停止：`./stop.sh` ｜ 改采集目标：编辑 `config.py` 的 `FIDS`

## 核心脚本

| 文件 | 作用 |
|---|---|
| `config.py` | 集中配置（目标板块、间隔、输出名） |
| `scraper_collect.py` | 主采集脚本（列表 → 详情，22 字段） |
| `check_env.py` | 换机环境自检 |
| `start.sh` / `stop.sh` | 一键启停 |
| `analyze.py` | 生成《采集质量与分布报告.md》+《回复时延分布.csv》 |
| `monitor_complete.py` | 采完自动出报告 + 导出原始数据到 `results/` |
| `count_all.py` | 侦察：统计各板块可采集总量 |

## 采集结果

- 输出：`collected_1217_1218.jsonl`（每行一条 JSON，22 字段）
- 当前已采：广州市委书记(1217) 1974 条 + 广州市市长(1218) 1374 条 = **3348 条**
- 时间跨度：2024-08 ~ 2026-08（受站点「仅开放近两年」限制）
- 分析产物：`results/` 目录（原始数据 jsonl + CSV）、`采集质量与分布报告.md`

## 关键约束（详见交接文档）

1. 请求间隔**必须**保持：列表 9 秒、详情 4.5~6 秒 —— 3.5 秒会 403。
2. 列表参数 `showUnAnswer` **必须为 1**，否则漏掉所有未回复留言。
3. 断点续跑基于输出文件中的 tid；**重采同一板块需先删除** `collected_*.jsonl` 与 `list_*.json`。
4. 长时运行需防休眠（macOS：`caffeinate -i ./start.sh`）。

## 废弃脚本

`scraper.py`、`click_more.py`、`probe_pages.py` 等为早期 Playwright 探索版本（需装 playwright），**已不再使用**，可删除。

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
采集完成后的数据校验与分布分析 -> 输出 report.md + 回复时延分布.csv
读取 collected_1217_1218.jsonl, 产出:
  1) 字段完整性校验(各字段缺失率)
  2) 办理状态分布(state_info)
  3) 回复率
  4) 回复时延分布(均值/中位数/分位/天数桶)
  5) 留言时间分布(按月)
  6) 满意度分布(有回复样本)
"""
import json, os, sys, time, statistics, csv, argparse
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _p in (ROOT, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---- 读集中配置(缺失则用兜底值) ----
try:
    import config as CFG
    OUT = CFG.OUT
    FID_NAME = {fid: name for fid, name in CFG.ALL_FIDS}
except Exception:
    OUT = os.path.join(ROOT, "collected_all13_20260914.jsonl")
    FID_NAME = {}

REPORT = os.path.join(ROOT, "docs", "采集质量与分布报告.md")
DELAY_CSV = os.path.join(ROOT, "results", "回复时延分布.csv")

FIELDS = ["tid","fid","forum_name","subject","type_name","domain_name","state_info",
          "nick_name","create_dateline","create_date","content","satisfaction","from",
          "ip_place","reply_content","reply_organization","reply_dateline","reply_date",
          "reply_nick_name","has_reply","reply_delay_days","reply_dept_level"]

def load(path):
    recs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except Exception:
                pass
    return recs

def is_missing(v):
    return v is None or v == ""

def main():
    ap = argparse.ArgumentParser(description="采集质量与分布报告生成")
    ap.add_argument("--input", default=OUT, help="collected_*.jsonl 路径")
    ap.add_argument("--out", default=REPORT, help="输出 Markdown 路径")
    ap.add_argument("--delay-csv", default=DELAY_CSV, help="输出时延分布 CSV 路径")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"[x] 找不到数据文件: {args.input}")
        return 2

    recs = load(args.input)
    n = len(recs)
    print(f"加载记录: {n} 条")
    fid_c = Counter(r.get("fid") for r in recs)
    scope = " + ".join(FID_NAME.get(f, str(f)) for f in sorted(fid_c))
    L = []
    L.append(f"# 人民网领导留言板 · 广州市 采集质量与分布报告")
    L.append(f"\n- 板块范围: {len(fid_c)} 个（{scope}）")
    L.append(f"- 数据文件: `{os.path.basename(args.input)}`")
    L.append(f"- 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    L.append(f"- 记录总数: **{n}** 条\n")
    L.append("> 本报告只含聚合统计量，不含任何留言正文、标题或昵称。\n")

    # 1. 板块分布
    L.append("## 1. 板块分布")
    for fid, cnt in sorted(fid_c.items(), key=lambda x: -x[1]):
        L.append(f"- {FID_NAME.get(fid, fid)} (fid={fid}): {cnt} 条")
    L.append("")

    # 2. 字段完整性
    L.append("## 2. 字段完整性校验")
    L.append("| 字段 | 缺失数 | 缺失率 |")
    L.append("|------|--------|--------|")
    miss = {}
    for fld in FIELDS:
        m = sum(1 for r in recs if is_missing(r.get(fld)))
        miss[fld] = m
        L.append(f"| {fld} | {m} | {m/n*100:.1f}% |")
    L.append("")
    L.append("**学术分析关键字段缺失:**")
    for fld in ["content", "reply_content", "reply_delay_days", "state_info",
                "create_date", "subject", "type_name"]:
        L.append(f"- {fld}: 缺失 {miss[fld]} ({miss[fld]/n*100:.1f}%)")
    L.append("")

    # 3. 办理状态分布
    L.append("## 3. 办理状态分布")
    st_c = Counter((r.get("state_info") or "未知") for r in recs)
    L.append("| 状态 | 条数 | 占比 |")
    L.append("|------|------|------|")
    for st, cnt in st_c.most_common():
        L.append(f"| {st} | {cnt} | {cnt/n*100:.1f}% |")
    L.append("")

    # 4. 回复率
    replied = sum(1 for r in recs if r.get("has_reply") == 1)
    L.append("## 4. 回复率")
    L.append(f"- 有官方回复: {replied} 条 ({replied/n*100:.1f}%)")
    L.append(f"- 无回复(待回复/未回复): {n-replied} 条 ({(n-replied)/n*100:.1f}%)\n")

    # 5. 回复时延分布
    L.append("## 5. 回复时延分布")
    delays = [r["reply_delay_days"] for r in recs
              if isinstance(r.get("reply_delay_days"), (int, float))]
    neg = sum(1 for d in delays if d < 0)
    L.append(f"- 有效时延样本: {len(delays)} 条")
    if neg:
        L.append(f"- ⚠️ 负值(回复早于留言, 数据异常): {neg} 条")
    if delays:
        ds = sorted(delays)
        mean = statistics.mean(delays)
        med = statistics.median(delays)
        sd = statistics.pstdev(delays) if len(delays) > 1 else 0
        p25 = ds[int(len(ds) * 0.25)]
        p75 = ds[int(len(ds) * 0.75)]
        p90 = ds[int(len(ds) * 0.90)]
        L.append(f"- 均值: {mean:.2f} 天 | 中位数: {med:.2f} 天 | 标准差: {sd:.2f} 天")
        L.append(f"- 最小: {min(delays):.2f} | 最大: {max(delays):.2f}")
        L.append(f"- 分位数 P25 / P75 / P90: {p25:.2f} / {p75:.2f} / {p90:.2f} 天")
        buckets = [(0, 1, "0–1天"), (1, 3, "1–3天"), (3, 7, "3–7天"),
                   (7, 15, "7–15天"), (15, 30, "15–30天"), (30, 60, "30–60天"),
                   (60, 90, "60–90天"), (90, 1e9, ">90天")]
        L.append("\n**时延分布(天数桶):**\n")
        L.append("| 区间 | 条数 | 占比 |")
        L.append("|------|------|------|")
        hist = {}
        for lo, hi, lab in buckets:
            c = sum(1 for d in delays if lo <= d < hi)
            hist[lab] = c
            L.append(f"| {lab} | {c} | {c/len(delays)*100:.1f}% |")
        os.makedirs(os.path.dirname(os.path.abspath(args.delay_csv)), exist_ok=True)
        with open(args.delay_csv, "w", newline="", encoding="utf-8-sig") as cf:
            w = csv.writer(cf)
            w.writerow(["区间", "条数", "占比"])
            for lo, hi, lab in buckets:
                w.writerow([lab, hist[lab], f"{hist[lab]/len(delays)*100:.1f}%"])
        L.append("")

    # 6. 留言时间分布(按月)
    L.append("## 6. 留言时间分布(按月)")
    mc = Counter()
    for r in recs:
        cd = r.get("create_date")
        if cd:
            mc[cd[:7]] += 1
    L.append("| 月份 | 条数 |")
    L.append("|------|------|")
    for m, cnt in sorted(mc.items()):
        L.append(f"| {m} | {cnt} |")
    L.append("")

    # 7. 满意度分布(有回复样本)
    L.append("## 7. 满意度分布(有回复样本中)")
    sat_c = Counter(r.get("satisfaction") for r in recs if r.get("has_reply") == 1)
    L.append("| 满意度 | 条数 |")
    L.append("|--------|------|")
    for sat, cnt in sorted(sat_c.items(), key=lambda x: -x[1]):
        L.append(f"| {sat} | {cnt} |")
    L.append("")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"报告已写出: {args.out}")
    print("DONE")
    return 0

if __name__ == "__main__":
    sys.exit(main())

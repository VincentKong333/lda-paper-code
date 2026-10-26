#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回复时延 · 生存分析（辅助分析，非主研究）
================================================================
把"未回复"按右删失处理，避免朴素口径的存活者偏差（实测低估中位时延 17.4%）。

产出（results/ 下）：
  生存分析_KM分组.csv     各组中位生存时间 + 事件数 + 删失数
  生存分析_logrank.csv    分组 log-rank 检验 p 值
  生存分析_Cox结果.csv    Cox 比例风险模型：HR / 95%CI / p
  生存分析报告.md         汇总报告（论文方法章可直接引用）
  fig_KM曲线.png          Kaplan-Meier 曲线图
  fig_Cox森林图.png       Cox 风险比森林图

用法：
  python survival_cox.py --input collected_1217_1218.jsonl --censor "2026-08-24 17:13:19"
  python survival_cox.py                      # 默认读 config.OUT，删失时刻自动推断
"""
import argparse
import csv
import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import config as CFG

RESULT_DIR = CFG.RESULT_DIR
CITY_FIDS = {1217, 1218}
FID_NAME = dict(CFG.ALL_FIDS)


def set_cjk_font():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def auto_censor():
    """取最新一次采集日志的修改时间作为统一删失时刻。"""
    cands = [os.path.join(HERE, f) for f in os.listdir(HERE)
             if f.startswith("scraper_run_") and f.endswith(".log")]
    if cands:
        return int(os.path.getmtime(max(cands, key=os.path.getmtime)))
    return None


def build_frame(path, censor_ts):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            c = int(r.get("create_dateline") or 0)
            if not c:
                continue
            if r.get("has_reply") and r.get("reply_dateline"):
                T, E = (int(r["reply_dateline"]) - c) / 86400.0, 1
            else:
                T, E = (censor_ts - c) / 86400.0, 0
            if T < 0:          # 回复早于留言，异常
                continue
            rows.append({
                "tid": r.get("tid"),
                "创建TS": c,
                "季": f"{(r.get('create_date') or '2025-01')[:4]}"
                     f"Q{((int((r.get('create_date') or '2025-01')[5:7]) - 1) // 3) + 1}",
                "T": T,
                "E": E,
                "板块": FID_NAME.get(r.get("fid"), str(r.get("fid"))),
                "层级": "市级" if r.get("fid") in CITY_FIDS else "区级",
                "类型": r.get("type_name") or "未知",
                "领域": r.get("domain_name") or "未知",
                "年份": int((r.get("create_date") or "2025")[:4]),
                "正文长度": len(r.get("content") or ""),
                "标题长度": len(r.get("subject") or ""),
            })
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=CFG.OUT)
    ap.add_argument("--censor", default=None, help='删失时刻, 如 "2026-08-24 17:13:19"')
    ap.add_argument("--top-domain", type=int, default=6)
    ap.add_argument("--year-mode", choices=["factor", "numeric"], default="factor",
                    help="年份进入 Cox 的方式。factor=分类(默认); numeric=线性趋势。"
                         "注意：实测回复速度随年份非单调(呈U形)，用 numeric 会强行拟合线性趋势。")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"[未就绪] 找不到数据文件: {args.input}")
        print("         若想先用旧数据试跑，加 --input collected_1217_1218.jsonl")
        sys.exit(2)

    if args.censor:
        censor_ts = int(time.mktime(time.strptime(args.censor, "%Y-%m-%d %H:%M:%S")))
    else:
        censor_ts = auto_censor()
        if censor_ts is None:
            print("[错误] 无法自动推断删失时刻，请用 --censor 显式指定")
            sys.exit(1)
    print("=" * 74)
    print("  回复时延 · 生存分析")
    print("=" * 74)
    print(f"输入     : {os.path.basename(args.input)}")
    print(f"删失时刻 : {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(censor_ts))}"
          f"  （此刻仍未回复者按右删失处理）")
    print()

    os.makedirs(RESULT_DIR, exist_ok=True)
    df = build_frame(args.input, censor_ts)
    n, ev, ce = len(df), int(df["E"].sum()), int((df["E"] == 0).sum())
    print(f"样本 {n} 条 | 事件(已回复) {ev} | 删失(未回复) {ce} = {ce/n*100:.1f}%")
    print(f"最大随访时长 {df['T'].max():.1f} 天 | 中位随访 {df['T'].median():.1f} 天")

    plt = set_cjk_font()
    from lifelines import KaplanMeierFitter, CoxPHFitter
    from lifelines.statistics import multivariate_logrank_test

    # ---------------- 1. 总体 KM ----------------
    kmf = KaplanMeierFitter()
    kmf.fit(df["T"], df["E"], label="总体")
    med_all = kmf.median_survival_time_
    print(f"\n[总体] KM 中位回复时延 = {med_all:.1f} 天  "
          f"(朴素口径只算已回复样本 = {df.loc[df.E==1,'T'].median():.1f} 天)")
    sfun = kmf.survival_function_
    for d in (30, 60, 90, 180, 365):
        try:
            v = float(sfun.loc[sfun.index <= d].iloc[-1, 0])
            print(f"        {d:>3} 天内已回复比例 = {1-v:.1%}")
        except Exception:
            pass

    # ---------------- 2. 分组 KM + log-rank ----------------
    groups = [("层级", None), ("板块", None), ("类型", None), ("领域", "top")]
    km_rows, lr_rows = [], []
    plotted = {}

    def fit_group(col, series):
        vals = series.value_counts()
        if col == "领域":
            vals = vals[vals >= 100]
        figs = []
        for v in vals.index:
            sub = df[series == v]
            if len(sub) < 30 or sub["E"].sum() < 5:
                continue
            f = KaplanMeierFitter().fit(sub["T"], sub["E"], label=str(v))
            km_rows.append({"分组维度": col, "组": v, "n": len(sub),
                            "事件": int(sub["E"].sum()),
                            "删失": int((sub["E"] == 0).sum()),
                            "删失率": f"{(sub['E']==0).mean()*100:.1f}%",
                            "KM中位(天)": round(float(f.median_survival_time_), 1)})
            figs.append((str(v), f))
        if len(figs) >= 2:
            Ts, Es, labels = [], [], []
            for v, _ in figs:
                sub = df[series == v]
                Ts.extend(sub["T"].tolist())
                Es.extend(sub["E"].tolist())
                labels.extend([str(v)] * len(sub))
            res = multivariate_logrank_test(np.array(Ts), np.array(labels),
                                            np.array(Es))
            lr_rows.append({"分组维度": col, "组数": len(figs),
                            "log-rank统计量": round(float(res.test_statistic), 3),
                            "p值": round(float(res.p_value), 5),
                            "显著性": "***" if res.p_value < 0.001 else
                                      "**" if res.p_value < 0.01 else
                                      "*" if res.p_value < 0.05 else "n.s."})
        plotted[col] = figs

    fit_group("层级", df["层级"])
    fit_group("板块", df["板块"])
    fit_group("类型", df["类型"])
    fit_group("领域", df["领域"])

    print("\n[分组 KM 中位]")
    for r in km_rows:
        print(f"    {r['分组维度']:<4} {r['组']:<12} n={r['n']:>5} "
              f"删失={r['删失率']:>6} 中位={r['KM中位(天)']:>7} 天")
    print("\n[log-rank 检验]")
    for r in lr_rows:
        print(f"    按 {r['分组维度']:<4} 分组: χ²={r['log-rank统计量']:>8}  "
              f"p={r['p值']:<8} {r['显著性']}")

    # ---------------- 3. KM 曲线图 ----------------
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    ax = axes[0]
    kmf.plot_survival_function(ax=ax, ci_show=True, color="#185FA5", linewidth=2)
    ax.axhline(0.5, color="#B4B2A9", linestyle="--", linewidth=1)
    ax.axvline(med_all, color="#E24B4A", linestyle=":", linewidth=1)
    ax.annotate(f"中位 {med_all:.1f} 天", xy=(med_all, 0.5),
                xytext=(med_all + 30, 0.62), fontsize=11, color="#A32D2D",
                arrowprops=dict(arrowstyle="->", color="#A32D2D", lw=1))
    ax.set_xlabel("留言提交后天数")
    ax.set_ylabel("尚未回复比例 S(t)")
    ax.set_title("总体 KM 回复生存曲线", fontsize=12)
    ax.set_xlim(0, 400)
    ax.set_ylim(0, 1.02)

    ax = axes[1]
    colors = ["#185FA5", "#D85A30", "#1D9E75", "#7F77DD", "#BA7517", "#D4537E"]
    for i, (lab, f) in enumerate(plotted.get("板块", [])[:6]):
        f.plot_survival_function(ax=ax, ci_show=False, label=lab,
                                 color=colors[i % len(colors)], linewidth=1.8)
    ax.axhline(0.5, color="#B4B2A9", linestyle="--", linewidth=1)
    ax.set_xlabel("留言提交后天数")
    ax.set_ylabel("尚未回复比例 S(t)")
    ax.set_title("分板块 KM 曲线", fontsize=12)
    ax.set_xlim(0, 400)
    ax.set_ylim(0, 1.02)
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(RESULT_DIR, "fig_KM曲线.png"), dpi=160)
    print(f"\n[图] results/fig_KM曲线.png")

    # ---------------- 3b. 队列稳健性（按提交季度） ----------------
    # 关键：一个队列的"90天回复率"只有在保证随访 >= 90 天时才可比。
    # 保证随访 = 删失时刻 - 该队列最晚一条留言的提交时刻。
    print("\n[队列稳健性] 按提交季度（保证随访不足的队列，其90天回复率不可比）")
    print(f"    {'队列':<8}{'n':>6}{'删失':>7}{'保证随访':>9}{'KM中位':>8}{'90天回复率':>11}")
    q_rows = []
    for q, sub in df.groupby("季"):
        if len(sub) < 30:
            continue
        min_fu = (censor_ts - sub["创建TS"].max()) / 86400.0
        f = KaplanMeierFitter().fit(sub["T"], sub["E"])
        med = f.median_survival_time_
        sf = f.survival_function_
        idx = sf.index[sf.index <= 90]
        s90 = float(sf.loc[idx].iloc[-1, 0]) if len(idx) else 1.0
        comparable = min_fu >= 120
        q_rows.append({"队列": q, "n": len(sub),
                       "事件": int(sub["E"].sum()),
                       "删失": int((sub["E"] == 0).sum()),
                       "保证随访(天)": round(min_fu),
                       "KM中位(天)": round(med, 1) if med != np.inf else None,
                       "90天回复率": f"{1-s90:.1%}" if comparable else "随访不足",
                       "可比": "是" if comparable else "否"})
        print(f"    {q:<8}{len(sub):>6}{int((sub['E']==0).sum()):>7}"
              f"{min_fu:>9.0f}{(round(med,1) if med!=np.inf else 0):>8.0f}"
              f"{(f'{1-s90:.1%}' if comparable else '随访不足'):>11}")

    # ---------------- 4. Cox 比例风险 ----------------
    cx = df.copy()
    cx["正文长度"] = np.log1p(cx["正文长度"])
    if args.year_mode == "factor":
        cx["年份"] = cx["年份"].astype(str)
    top_dom = cx["领域"].value_counts().head(args.top_domain).index.tolist()
    cx["领域"] = cx["领域"].where(cx["领域"].isin(top_dom), "其他")
    drop = ["tid", "T", "E", "创建TS", "季"]
    X = cx.drop(columns=drop + ["标题长度"])
    X = pd.get_dummies(X, drop_first=True)
    X = X.astype(float)
    X["T"] = cx["T"].values
    X["E"] = cx["E"].values

    cph = CoxPHFitter(penalizer=0.01)
    cph.fit(X, duration_col="T", event_col="E")
    summ = cph.summary
    print(f"\n[Cox 比例风险] 协变量 {len(summ)} 个 | 事件 {ev} | "
          f"Concordance = {cph.concordance_index_:.3f}")
    print(summ[["coef", "exp(coef)", "exp(coef) lower 95%",
                "exp(coef) upper 95%", "p"]].round(3).to_string())

    with open(os.path.join(RESULT_DIR, "生存分析_Cox结果.csv"), "w", newline="",
              encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["协变量", "系数", "HR", "95%CI下限", "95%CI上限", "p值", "显著性"])
        for name, row in summ.iterrows():
            p = float(row["p"])
            w.writerow([name, round(float(row["coef"]), 4), round(float(row["exp(coef)"]), 4),
                        round(float(row["exp(coef) lower 95%"]), 4),
                        round(float(row["exp(coef) upper 95%"]), 4), round(p, 5),
                        "***" if p < 0.001 else "**" if p < 0.01 else
                        "*" if p < 0.05 else "n.s."])

    # 森林图
    fig2, ax2 = plt.subplots(figsize=(9, max(3.5, 0.42 * len(summ) + 1.5)))
    s = summ.sort_values("exp(coef)")
    y = np.arange(len(s))
    hr = s["exp(coef)"].values
    lo = s["exp(coef) lower 95%"].values
    hi = s["exp(coef) upper 95%"].values
    ax2.errorbar(hr, y, xerr=[hr - lo, hi - hr], fmt="o", color="#185FA5",
                 ecolor="#85B7EB", capsize=3, markersize=6)
    ax2.axvline(1.0, color="#B4B2A9", linestyle="--", linewidth=1)
    ax2.set_yticks(y)
    ax2.set_yticklabels(s.index, fontsize=9)
    ax2.set_xscale("log")
    ax2.set_xlabel("风险比 HR（对数刻度；>1 = 回复更快，<1 = 回复更慢）", fontsize=10)
    ax2.set_title("Cox 比例风险模型 · 森林图", fontsize=12)
    fig2.tight_layout()
    fig2.savefig(os.path.join(RESULT_DIR, "fig_Cox森林图.png"), dpi=160)
    print(f"[图] results/fig_Cox森林图.png")

    # ---------------- 5. 落盘 ----------------
    pd.DataFrame(lr_rows).to_csv(os.path.join(RESULT_DIR, "生存分析_logrank.csv"),
                                 index=False, encoding="utf-8-sig")
    pd.DataFrame(km_rows).to_csv(os.path.join(RESULT_DIR, "生存分析_KM分组.csv"),
                                 index=False, encoding="utf-8-sig")
    pd.DataFrame(q_rows).to_csv(os.path.join(RESULT_DIR, "生存分析_队列稳健性.csv"),
                                index=False, encoding="utf-8-sig")
    sfun.to_csv(os.path.join(RESULT_DIR, "生存分析_总体KM曲线.csv"), encoding="utf-8-sig")

    L = ["# 回复时延 · 生存分析报告", "",
         f"- 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
         f"- 输入文件: `{os.path.basename(args.input)}`",
         f"- 删失时刻: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(censor_ts))}",
         f"- 样本: **{n} 条**（事件 {ev}，删失 {ce} = {ce/n*100:.1f}%）",
         f"- 中位随访时长: {df['T'].median():.1f} 天", "",
         "## 1. 总体结果", "",
         f"- **KM 中位回复时延 = {med_all:.1f} 天**",
         f"- 若只对已回复样本算中位数（朴素口径）= {df.loc[df.E==1,'T'].median():.1f} 天，"
         f"低估 {(med_all-df.loc[df.E==1,'T'].median())/med_all*100:.1f}%", ""]
    L.append("| 天数 | 已回复比例 |")
    L.append("|------|-----------|")
    for d in (30, 60, 90, 180, 365):
        try:
            v = float(sfun.loc[sfun.index <= d].iloc[-1, 0])
            L.append(f"| {d} | {1-v:.1%} |")
        except Exception:
            pass
    L += ["", "## 2. 分组比较（log-rank）", "",
          "| 分组维度 | 组数 | χ² | p | 显著性 |", "|---|---|---|---|---|"]
    for r in lr_rows:
        L.append(f"| {r['分组维度']} | {r['组数']} | {r['log-rank统计量']} | "
                 f"{r['p值']} | {r['显著性']} |")
    L += ["", "## 3. 各组 KM 中位时延", "",
          "| 维度 | 组 | n | 删失率 | KM中位(天) |", "|---|---|---|---|---|"]
    for r in km_rows:
        L.append(f"| {r['分组维度']} | {r['组']} | {r['n']} | {r['删失率']} | "
                 f"{r['KM中位(天)']} |")
    L += ["", "## 4. 队列稳健性（按提交季度）", "",
          "> 一个队列的「90 天回复率」只有在**保证随访 ≥ 120 天**时才可跨队列比较。",
          "> 保证随访 = 删失时刻 − 该队列最晚一条留言的提交时刻。", "",
          "| 队列 | n | 删失 | 保证随访(天) | KM中位(天) | 90天回复率 | 可比 |",
          "|---|---|---|---|---|---|---|"]
    for r in q_rows:
        L.append(f"| {r['队列']} | {r['n']} | {r['删失']} | {r['保证随访(天)']} | "
                 f"{r['KM中位(天)'] if r['KM中位(天)'] else '未达'} | "
                 f"{r['90天回复率']} | {r['可比']} |")
    L += ["", "## 5. Cox 比例风险模型", "",
          f"年份进入方式: **{args.year_mode}**（factor=分类；numeric=线性趋势）", "",
          f"Concordance index = {cph.concordance_index_:.3f}", "",
          "| 协变量 | HR | 95%CI | p | 显著性 |", "|---|---|---|---|---|"]
    for name, row in summ.iterrows():
        p = float(row["p"])
        L.append(f"| {name} | {float(row['exp(coef)']):.3f} | "
                 f"[{float(row['exp(coef) lower 95%']):.3f}, "
                 f"{float(row['exp(coef) upper 95%']):.3f}] | {p:.4f} | "
                 f"{'***' if p<0.001 else '**' if p<0.01 else '*' if p<0.05 else 'n.s.'} |")
    L += ["", "> **HR 方向**：HR>1 表示该组回复速度更快（等待更短）；HR<1 表示回复更慢。",
          "> 基准组 = `drop_first` 后作为参照的水平，解释时须指明。", "",
          "## 6. 图表", "",
          "- `fig_KM曲线.png` — 总体与分板块 KM 曲线（论文图 1）",
          "- `fig_Cox森林图.png` — Cox 风险比森林图（论文图 2）", "",
          "## 7. 方法学备注（可直接写入论文）", "",
          "- 时间原点：留言提交时间；事件：首次官方回复时间。",
          "- 采集时点仍未回复者按**右删失**处理，删失时长为采集时刻减提交时刻。",
          "- 删失由采集时点决定、与留言内容无关，满足**非信息删失**假设。",
          "- 生存函数用 Kaplan-Meier 估计，组间差异用 log-rank 检验，",
          "  多因素用 Cox 比例风险模型（含板块、类型、领域、年份、正文长度等协变量）。",
          "- **年份务必按分类变量进入模型**：实测回复速度随年份非单调（呈 U 形，",
          "  见第 4 节），若按线性数值处理会强行拟合出单调趋势，结论失真。",
          "- 引用第 4 节时，只比较**保证随访 ≥ 120 天**的队列（该列标为「是」），",
          "  标注「随访不足」的队列其 90 天回复率尚未观测完整，不可与其它队列并列。", ""]
    open(os.path.join(RESULT_DIR, "生存分析报告.md"), "w", encoding="utf-8").write("\n".join(L))
    print("[报告] results/生存分析报告.md")
    print("=" * 74)


if __name__ == "__main__":
    main()

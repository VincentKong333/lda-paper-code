#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回复时延：朴素口径 vs 生存分析口径 对照演示
================================================================
用本地 3348 条实测数据，量化"只算已回复样本"会低估多少。
零依赖，手写 Kaplan-Meier 与 log-rank，便于论文复现。

口径说明：
  - 朴素口径A(低估): 只在 has_reply=1 的样本上算均值/中位数
  - 朴素口径B(高估): 把未回复者当作"永不回复", 时延取到随访截止
  - KM 口径(正确): 未回复者作为右删失, 只用风险集估计 S(t)

随访截止: 旧数据为 2026-08-19~08-24 多次运行, 此处统一取
          results/DONE.txt 记录的完成时刻 2026-08-24 17:13:19。
用法: python survival_demo.py
"""
import json
import os
import sys
import time
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
CENSOR_TS = int(time.mktime(time.strptime("2026-08-24 17:13:19", "%Y-%m-%d %H:%M:%S")))
SRC = os.path.join(HERE, "collected_1217_1218.jsonl")


def build():
    """返回 [(fid, duration_days, event), ...]"""
    out = []
    for line in open(SRC, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        c = int(r.get("create_dateline") or 0)
        if not c:
            continue
        if r.get("has_reply") and r.get("reply_dateline"):
            d = (int(r["reply_dateline"]) - c) / 86400.0
            e = 1
        else:
            d = (CENSOR_TS - c) / 86400.0
            e = 0
        if d < 0:
            continue
        out.append((r.get("fid"), d, e, r.get("state_info")))
    return out


def km(data):
    """手写 Kaplan-Meier。返回 (times, survivals, median, s_at)"""
    ev_times = sorted({d for _, d, e, _ in data if e == 1})
    n = len(data)
    times, surv = [], []
    s = 1.0
    S = {}
    for t in ev_times:
        at_risk = sum(1 for _, d, _, _ in data if d >= t)
        deaths = sum(1 for _, d, e, _ in data if e == 1 and d == t)
        if at_risk == 0:
            continue
        s *= (1 - deaths / at_risk)
        times.append(t)
        surv.append(s)
        S[t] = s
    med = next((t for t in times if S[t] <= 0.5), None)
    return times, surv, med, S


def s_at(times, surv, q):
    v = None
    for t, s in zip(times, surv):
        if t <= q:
            v = s
        else:
            break
    return v


def logrank(g1, g2):
    """两样本 log-rank 检验, 返回 (chi2, p)"""
    events = sorted({d for _, d, e, _ in g1 + g2 if e == 1})
    O1 = E1 = V = 0.0
    all_ = g1 + g2
    for t in events:
        n = sum(1 for _, d, _, _ in all_ if d >= t)
        n1 = sum(1 for _, d, _, _ in g1 if d >= t)
        d = sum(1 for _, dd, e, _ in all_ if e == 1 and dd == t)
        d1 = sum(1 for _, dd, e, _ in g1 if e == 1 and dd == t)
        if n <= 1:
            continue
        O1 += d1
        E1 += d * n1 / n
        V += d * (n1 / n) * (1 - n1 / n) * (n - d) / (n - 1)
    if V == 0:
        return 0.0, 1.0
    chi2 = (O1 - E1) ** 2 / V
    # 卡方 df=1 的 p 值, 用 erfc 近似
    import math
    p = math.erfc(math.sqrt(chi2 / 2))
    return chi2, p


def curve_binned(times, surv, step=14):
    """按 step 天分箱, 取箱末的 S(t), 便于绘图"""
    pts = []
    t = step
    while t <= int(times[-1]) + step:
        v = s_at(times, surv, t)
        if v is None:
            v = 1.0
        pts.append((t, round(v, 4)))
        t += step
    return pts


def main():
    data = build()
    events = [x for x in data if x[2] == 1]
    cens = [x for x in data if x[2] == 0]
    print("=" * 70)
    print("  回复时延：三种口径对照")
    print("=" * 70)
    print(f"总样本 {len(data)} 条 | 已回复(事件) {len(events)} | 未回复(删失) {len(cens)} "
          f"= {len(cens)/len(data)*100:.1f}%")
    print()
    print("[状态字段核对]")
    st = collections.Counter((x[3], x[2]) for x in data)
    for (s, e), c in st.most_common():
        print(f"  stateInfo={s!r:<12} has_reply={e}  {c} 条")
    print()

    de = sorted(d for _, d, e, _ in events)
    q = lambda a, p: a[int(p * (len(a) - 1))]
    print("[口径A 朴素·只算已回复]  <<< 最常被误用")
    print(f"  均值 {sum(de)/len(de):.1f} 天 | 中位 {q(de,.5):.1f} | p75 {q(de,.75):.1f} "
          f"| p90 {q(de,.9):.1f} | p95 {q(de,.95):.1f}")

    dall = sorted(d for _, d, _, _ in data)
    print("[口径B 朴素·未回复当永不回复]")
    print(f"  均值 {sum(dall)/len(dall):.1f} 天 | 中位 {q(dall,.5):.1f} | p75 {q(dall,.75):.1f} "
          f"| p90 {q(dall,.9):.1f}")
    n_cens = sum(1 for x in data if x[2] == 0)
    print(f"  (该口径把 {n_cens} 条未回复者按【永不回复】计入, 属人为强假设, 会高估)")

    times, surv, med, S = km(data)
    print("[口径C Kaplan-Meier 生存分析]  <<< 正确口径")
    print(f"  中位时延 S(t)=0.5 处: {med:.1f} 天")
    for d in (7, 30, 60, 90, 180, 365):
        v = s_at(times, surv, d)
        if v is not None:
            print(f"  S({d:>3}天) = {v:.3f}  ->  该期限内已回复比例 {1-v:.1%}")
    print()
    print(f"[结论] 朴素口径中位 {q(de,.5):.1f} 天  vs  KM 中位 {med:.1f} 天"
          f"  ->  低估 {(med-q(de,.5))/med*100:.1f}%")
    print()

    g1 = [x for x in data if x[0] == 1217]
    g2 = [x for x in data if x[0] == 1218]
    print("[分组对比 1217 vs 1218 · log-rank]")
    for nm, g in (("市委书记 1217", g1), ("市长 1218", g2)):
        t2, s2, m2, _ = km(g)
        ce = sum(1 for x in g if x[2] == 0)
        print(f"  {nm}: n={len(g)} 删失={ce}({ce/len(g)*100:.1f}%) KM中位={m2:.1f} 天")
    chi2, p = logrank(g1, g2)
    print(f"  log-rank chi2 = {chi2:.3f}, p = {p:.4f}")
    print("=" * 70)

    json.dump({
        "censor_ts": CENSOR_TS,
        "n": len(data), "events": len(events), "censored": len(cens),
        "naive_replied_median": round(q(de, .5), 2),
        "naive_all_median": round(q(dall, .5), 2),
        "km_median": round(med, 2),
        "km_curve_1217": curve_binned(*km(g1)[:2]),
        "km_curve_1218": curve_binned(*km(g2)[:2]),
        "km_median_1217": km(g1)[2], "km_median_1218": km(g2)[2],
        "logrank_p": round(p, 5),
    }, open(os.path.join(HERE, "survival_demo_result.json"), "w", encoding="utf-8"),
        ensure_ascii=False, indent=2)
    print("曲线已写入 survival_demo_result.json")


if __name__ == "__main__":
    main()

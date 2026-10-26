#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
留言内容 LDA 主题建模流水线（研究主分析）
================================================================
输入 : config.OUT (jsonl, 每行一条 22 字段记录)
输出 : results/ 下
        lda_k_selection.csv      主题数选择：K / 困惑度 / UMass 一致性
        lda_topics.csv           每个主题的 top 词 + 权重 + 占比
        lda_doc_topic.csv        每条留言的主主题 + 概率（供后续统计）
        lda_topic_by_domain.csv  主题 × 官方领域分类（效度验证）
        lda_topic_by_type.csv    主题 × 留言类型（投诉求助/建言/咨询）
        lda_topic_by_board.csv   主题 × 板块（市级/区级）
        lda_topic_by_year.csv    主题 × 年份（主题演化）
        LDA内容分析报告.md

设计要点
  - 主题数不拍脑袋：对 K 网格逐点拟合，报困惑度与 UMass 一致性，取一致性峰值
  - UMass 一致性自行实现（只需共现计数），不依赖 gensim
  - 词表可编辑：stopwords.txt / userdict.txt，跑完看报告再迭代
  - 效度交叉验证：LDA 是无监督的，用官方 domain_name 检验主题是否可解释

用法
  python content_lda.py                     # 全量，K=6..20 步长2
  python content_lda.py --kmin 8 --kmax 16 --kstep 2
  python content_lda.py --sample 800        # 快速试跑
"""
import argparse
import csv
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import config as CFG

RESULT_DIR = CFG.RESULT_DIR
CITY_FIDS = {1217, 1218}          # 市级板块

# ---- 清洗正则 ----
RE_EMOJI = re.compile(r"\[[^\]]{1,8}\]")
RE_BRACKET = re.compile(r"[【】\[\]（）()<>《》]")
RE_SPACE = re.compile(r"\s+")
RE_URL = re.compile(r"https?://\S+|www\.\S+")
RE_PHONE = re.compile(r"1[3-9]\d{9}")
RE_ID = re.compile(r"\d{17}[\dXx]")
RE_EMAIL = re.compile(r"[\w.\-]+@[\w\-]+\.\w+")
RE_DUP = re.compile(r"(.)\1{3,}")          # 连续重复字符
RE_ASCII = re.compile(r"^[a-zA-Z0-9_\-]+$")


def load_texts(path):
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


def clean(t):
    if not t:
        return ""
    t = RE_URL.sub(" ", t)
    t = RE_EMAIL.sub(" ", t)
    t = RE_PHONE.sub(" ", t)
    t = RE_ID.sub(" ", t)
    t = RE_EMOJI.sub(" ", t)
    t = RE_BRACKET.sub(" ", t)
    t = RE_DUP.sub(r"\1", t)
    t = RE_SPACE.sub(" ", t)
    return t.strip()


def load_wordlist(fn):
    p = os.path.join(HERE, fn)
    out = set()
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            w = line.strip()
            if w and not w.startswith("#"):
                out.add(w)
    return out


def build_tokenizer():
    import jieba
    jieba.setLogLevel(60)
    ud = os.path.join(HERE, "userdict.txt")
    if os.path.exists(ud):
        jieba.load_userdict(ud)
    stop = load_wordlist("stopwords.txt")
    cache = {}

    def tok(text):
        if text in cache:
            return cache[text]
        words = []
        for w in jieba.lcut(text):
            w = w.strip()
            if len(w) < 2:
                continue
            if RE_ASCII.match(w):
                continue
            if w in stop:
                continue
            words.append(w)
        cache[text] = words
        return words

    return tok, stop


def umass_coherence(Xbin, df, top_idx, n_pairs_cap=50):
    """UMass 一致性: sum log((D(wi,wj)+1)/D(wj)) / pair_count"""
    if len(top_idx) < 2:
        return float("nan")
    co = Xbin.T.dot(Xbin)
    s, c = 0.0, 0
    for i in range(1, len(top_idx)):
        for j in range(i):
            wi, wj = int(top_idx[i]), int(top_idx[j])
            dij = co[wi, wj]
            dj = df[wj]
            if dj == 0:
                continue
            s += math.log((dij + 1.0) / dj)
            c += 1
    return s / c if c else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=CFG.OUT)
    ap.add_argument("--kmin", type=int, default=6)
    ap.add_argument("--kmax", type=int, default=20)
    ap.add_argument("--kstep", type=int, default=2)
    ap.add_argument("--topn", type=int, default=15)
    ap.add_argument("--min-df", type=int, default=5)
    ap.add_argument("--max-df", type=float, default=0.5)
    ap.add_argument("--min-len", type=int, default=20)
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--coherence-n", type=int, default=15)
    args = ap.parse_args()

    from sklearn.feature_extraction.text import CountVectorizer
    from sklearn.decomposition import LatentDirichletAllocation

    os.makedirs(RESULT_DIR, exist_ok=True)
    t_start = time.time()

    # ---------- 1. 读入与过滤 ----------
    if not os.path.exists(args.input):
        print(f"[未就绪] 找不到数据文件: {args.input}")
        print("         内容分析（LDA）依赖 13 板块全量采集结果。")
        print("         请先运行 run_scraper_win.py 完成采集；")
        print("         若只想用旧数据试跑，加参数：--input collected_1217_1218.jsonl")
        sys.exit(2)

    recs = load_texts(args.input)
    if not recs:
        print(f"[错误] 文件存在但没读到任何记录: {args.input}")
        sys.exit(1)

    n_raw = len(recs)
    kept, short, dedup = [], 0, 0
    seen = set()
    for r in recs:
        txt = clean((r.get("subject") or "") + "。" + (r.get("content") or ""))
        if len(txt) < args.min_len:
            short += 1
            continue
        key = txt
        if key in seen:
            dedup += 1
            continue
        seen.add(key)
        r["_text"] = txt
        kept.append(r)

    if args.sample and args.sample < len(kept):
        step = len(kept) / args.sample
        kept = [kept[int(i * step)] for i in range(args.sample)]
        print(f"[抽样] 快速试跑，随机取 {len(kept)} 条")

    print("=" * 70)
    print("  留言内容 LDA 主题建模")
    print("=" * 70)
    print(f"输入        : {os.path.basename(args.input)}")
    print(f"原始记录    : {n_raw}")
    print(f"过短剔除    : {short}  (清洗后 < {args.min_len} 字)")
    print(f"完全重复剔除: {dedup}")
    print(f"进入建模    : {len(kept)}")
    print()

    # ---------- 2. 分词 ----------
    tok, stop = build_tokenizer()
    print("[分词] jieba + userdict.txt 开始 ...", flush=True)
    texts = []
    for i, r in enumerate(kept):
        toks = tok(r["_text"])
        texts.append(toks)
        if (i + 1) % 2000 == 0:
            print(f"  已分词 {i+1}/{len(kept)} ...", flush=True)
    n_tok = sum(len(t) for t in texts)
    print(f"[分词] 完成，共 {n_tok} 个词例，平均每条 {n_tok/len(texts):.1f} 词")
    print(f"[停用词] {len(stop)} 条；[自定义词典] userdict.txt")
    print()

    # ---------- 3. 词频概览 ----------
    freq = Counter(w for t in texts for w in t)
    print("[高频词 Top 30]（若出现明显噪音，请加入 stopwords.txt 后重跑）")
    for w, c in freq.most_common(30):
        print(f"    {w:<10}{c:>6}  ({c/len(texts)*100:.1f}% 的留言出现)")
    print()

    # ---------- 4. 向量化 ----------
    vec = CountVectorizer(analyzer=lambda x: x, min_df=args.min_df,
                          max_df=args.max_df, token_pattern=None)
    X = vec.fit_transform(texts)
    vocab = vec.get_feature_names_out()
    print(f"[特征] 词典大小 {len(vocab)}（min_df={args.min_df}, max_df={args.max_df}）")
    Xbin = (X > 0).astype(np.int32)
    df_ = np.asarray(Xbin.sum(axis=0)).ravel()
    print()

    # ---------- 5. 主题数选择 ----------
    grid = list(range(args.kmin, args.kmax + 1, args.kstep))
    print(f"[主题数选择] K ∈ {grid}，逐点拟合（困惑度 + UMass 一致性）", flush=True)
    sel = []
    best_lda, best_k, best_coh = None, None, -1e9
    for k in grid:
        tk = time.time()
        lda = LatentDirichletAllocation(
            n_components=k, max_iter=25, learning_method="batch",
            random_state=args.seed, evaluate_every=5, n_jobs=1)
        lda.fit(X)
        perp = lda.perplexity(X)
        tops = np.argsort(-lda.components_, axis=1)[:, :args.coherence_n]
        cohs = [umass_coherence(Xbin, df_, t) for t in tops]
        coh = float(np.mean(cohs))
        sel.append((k, perp, coh))
        print(f"    K={k:>3}  困惑度={perp:>10.1f}  UMass一致性={coh:>8.4f}"
              f"  ({time.time()-tk:.0f}s)", flush=True)
        if coh > best_coh:
            best_coh, best_k, best_lda = coh, k, lda
    print(f"[主题数选择] 一致性最优 K = {best_k}（UMass={best_coh:.4f}）")
    print()

    lda = best_lda
    # ---------- 6. 主题词与主题-文档分布 ----------
    W = lda.components_
    doc_topic = lda.transform(X)
    dom_topic = doc_topic.argmax(axis=1)
    share = np.bincount(dom_topic, minlength=best_k) / len(kept)

    topics = []
    for i in range(best_k):
        idx = np.argsort(-W[i])[:args.topn]
        words = [(vocab[j], round(float(W[i][j]), 2)) for j in idx]
        topics.append({"topic": i, "share": share[i], "words": words,
                       "top_word": words[0][0]})

    with open(os.path.join(RESULT_DIR, "lda_topics.csv"), "w", newline="",
              encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["主题", "占比", "Top词", "Top词权重"])
        for t in topics:
            w.writerow([f"T{t['topic']}", f"{t['share']*100:.1f}%",
                        " / ".join(x[0] for x in t["words"]),
                        " / ".join(str(x[1]) for x in t["words"])])

    with open(os.path.join(RESULT_DIR, "lda_doc_topic.csv"), "w", newline="",
              encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["tid", "fid", "板块", "create_date", "type_name",
                    "domain_name", "主主题", "主题概率"])
        for i, r in enumerate(kept):
            w.writerow([r.get("tid"), r.get("fid"),
                        dict(CFG.ALL_FIDS).get(r.get("fid"), ""),
                        r.get("create_date"), r.get("type_name"),
                        r.get("domain_name"), f"T{dom_topic[i]}",
                        f"{float(doc_topic[i][dom_topic[i]]):.3f}"])

    # ---------- 7. 交叉表 ----------
    def crosstab(field, fn, label):
        rows = defaultdict(Counter)
        for i, r in enumerate(kept):
            v = r.get(field) or "未知"
            if field == "fid":
                v = "市级(1217/1218)" if r.get("fid") in CITY_FIDS else "区级(281x)"
            if field == "create_date":
                v = (r.get("create_date") or "")[:4]
            rows[v][f"T{dom_topic[i]}"] += 1
        cols = [f"T{i}" for i in range(best_k)]
        with open(os.path.join(RESULT_DIR, fn), "w", newline="",
                  encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow([label] + cols + ["合计"])
            for v in sorted(rows):
                tot = sum(rows[v].values())
                w.writerow([v] + [rows[v].get(c, 0) for c in cols] + [tot])
        return rows

    by_domain = crosstab("domain_name", "lda_topic_by_domain.csv", "官方领域")
    by_type = crosstab("type_name", "lda_topic_by_type.csv", "留言类型")
    by_board = crosstab("fid", "lda_topic_by_board.csv", "板块层级")
    by_year = crosstab("create_date", "lda_topic_by_year.csv", "年份")

    # ---------- 8. 效度验证：每个主题最"偏向"的官方领域 ----------
    valid = []
    for i in range(best_k):
        col = f"T{i}"
        best, best_ratio = None, -1
        for v, c in by_domain.items():
            tot = sum(c.values())
            if tot < 20:
                continue
            overall = sum(cc.get(col, 0) for cc in by_domain.values()) / len(kept)
            ratio = (c.get(col, 0) / tot) / overall if overall else 0
            if ratio > best_ratio:
                best, best_ratio = v, ratio
        valid.append((f"T{i}", best, best_ratio))

    # ---------- 9. 报告 ----------
    L = []
    L.append("# 留言内容 LDA 主题建模报告")
    L.append(f"\n- 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    L.append(f"- 输入文件: `{os.path.basename(args.input)}`")
    L.append(f"- 原始记录: {n_raw} 条（过短剔除 {short}，完全重复剔除 {dedup}）")
    L.append(f"- 建模样本: **{len(kept)} 条**")
    L.append(f"- 词典大小: {len(vocab)}（min_df={args.min_df}, max_df={args.max_df}）")
    L.append(f"- 选定主题数: **K = {best_k}**（UMass 一致性最优 {best_coh:.4f}，随机种子 {args.seed}）\n")

    L.append("## 1. 主题数选择")
    L.append("\n| K | 困惑度 | UMass 一致性 |")
    L.append("|---|--------|--------------|")
    for k, perp, coh in sel:
        mark = " ← 选中" if k == best_k else ""
        L.append(f"| {k} | {perp:.1f} | {coh:.4f}{mark} |")
    L.append("\n> 一致性越高表示主题内 top 词越倾向在同一篇留言共现，可解释性越好；"
             "困惑度随 K 单调下降，不能单独用于定 K。\n")

    L.append("## 2. 主题及高频词")
    for t in topics:
        L.append(f"\n### T{t['topic']}（占比 {t['share']*100:.1f}%）")
        L.append(f"- Top 词: {' / '.join(x[0] for x in t['words'])}")
        L.append(f"- 权重  : {' / '.join(str(x[1]) for x in t['words'])}")
    L.append("")

    L.append("## 3. 效度验证：主题 × 官方领域分类")
    L.append("\n每个主题最偏向的官方 `domain_name`（用于判断主题是否可解释）：\n")
    L.append("| 主题 | Top词 | 最偏向官方领域 | 偏向倍数 |")
    L.append("|------|-------|----------------|----------|")
    for (tid, dv, ratio), t in zip(valid, topics):
        L.append(f"| {tid} | {'、'.join(x[0] for x in t['words'][:6])} | {dv} | {ratio:.2f}x |")
    L.append("")

    L.append("## 4. 主题 × 留言类型")
    L.append("\n| 类型 | " + " | ".join(f"T{i}" for i in range(best_k)) + " | 合计 |")
    L.append("|" + "---|" * (best_k + 2))
    for v in sorted(by_type):
        c = by_type[v]
        L.append(f"| {v} | " + " | ".join(str(c.get(f'T{i}', 0)) for i in range(best_k))
                 + f" | {sum(c.values())} |")
    L.append("")

    L.append("## 5. 主题 × 板块层级")
    L.append("\n| 层级 | " + " | ".join(f"T{i}" for i in range(best_k)) + " | 合计 |")
    L.append("|" + "---|" * (best_k + 2))
    for v in sorted(by_board):
        c = by_board[v]
        L.append(f"| {v} | " + " | ".join(str(c.get(f'T{i}', 0)) for i in range(best_k))
                 + f" | {sum(c.values())} |")
    L.append("")

    L.append("## 6. 主题 × 年份")
    L.append("\n| 年份 | " + " | ".join(f"T{i}" for i in range(best_k)) + " | 合计 |")
    L.append("|" + "---|" * (best_k + 2))
    for v in sorted(by_year):
        c = by_year[v]
        L.append(f"| {v} | " + " | ".join(str(c.get(f'T{i}', 0)) for i in range(best_k))
                 + f" | {sum(c.values())} |")
    L.append("")

    L.append("## 7. 待办")
    L.append("- [ ] 人工为每个主题命名（依据第 2 节的 Top 词与代表性留言）")
    L.append("- [ ] 检查第 3 节：若某主题的最偏向领域偏向倍数 < 1.2，说明该主题与官方分类几乎无关，可能需要调 K")
    L.append("- [ ] 若第 2 节出现跨主题重复的高频噪音词，加入 `stopwords.txt` 后重跑")
    L.append("")

    with open(os.path.join(RESULT_DIR, "LDA内容分析报告.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    with open(os.path.join(RESULT_DIR, "lda_k_selection.csv"), "w", newline="",
              encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["K", "困惑度", "UMass一致性"])
        for k, perp, coh in sel:
            w.writerow([k, f"{perp:.1f}", f"{coh:.4f}"])

    print("=" * 70)
    print(f"  完成，用时 {time.time()-t_start:.0f}s")
    print(f"  主题报告   : results/LDA内容分析报告.md")
    print(f"  主题词表   : results/lda_topics.csv")
    print(f"  逐条主题   : results/lda_doc_topic.csv")
    print("=" * 70)


if __name__ == "__main__":
    main()

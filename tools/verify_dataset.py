#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据集核验脚本
================================================================
用途: 让审阅者在不接触原文的前提下, 确认某份 collected_*.jsonl
      确实是产出 results/ 下所有分析结果的那一份数据。

用法:
  # 1) 生成基线(作者侧, 只需跑一次, 结果随仓库发布)
  python tools/verify_dataset.py --input collected_all13_20260914.jsonl --write-baseline

  # 2) 核验(审阅者侧)
  python tools/verify_dataset.py --input 你手上的那份.jsonl

核对内容:
  - 文件 SHA-256 与字节数          -> 证明是同一份文件, 未被改动
  - 总条数 / 唯一 tid / 重复 tid    -> 证明没有拼接或重复计数
  - 时间范围 / 窗外条数            -> 证明严格遵守统一窗口
  - 各板块条数                     -> 证明覆盖面与报告一致
  - 关键字段缺失率 / 回复率 / 时延中位数 -> 证明描述统计可复现

注意: 脚本只读取统计量, 不打印任何留言原文。
================================================================
"""
import argparse
import hashlib
import json
import os
import statistics
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    import config as CFG
    DEFAULT_INPUT = CFG.OUT
    FID_NAME = {fid: name for fid, name in CFG.ALL_FIDS}
    WINDOW_START = CFG.WINDOW_START_TS
    WINDOW_END = CFG.WINDOW_END_TS
except Exception:
    DEFAULT_INPUT = os.path.join(ROOT, "collected_all13_20260914.jsonl")
    FID_NAME = {}
    WINDOW_START, WINDOW_END = 0, None

DEFAULT_BASELINE = os.path.join(ROOT, "docs", "数据基线.json")

KEY_FIELDS = ["content", "subject", "type_name", "domain_name", "state_info",
              "create_date", "reply_content", "reply_delay_days"]


def sha256_and_size(path):
    h = hashlib.sha256()
    size = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def collect_metrics(path):
    """只统计, 不保留任何正文字段。"""
    n = 0
    tids = set()
    dup = 0
    by_board = Counter()
    missing = Counter({f: 0 for f in KEY_FIELDS})
    dates = []
    out_of_window = 0
    replied = 0
    delays = []

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            n += 1

            tid = r.get("tid")
            if tid in tids:
                dup += 1
            else:
                tids.add(tid)

            fid = r.get("fid")
            by_board[FID_NAME.get(fid, f"fid={fid}")] += 1

            for fld in KEY_FIELDS:
                v = r.get(fld)
                if v is None or v == "":
                    missing[fld] += 1

            cd = r.get("create_date")
            if cd:
                dates.append(cd)

            ts = r.get("create_dateline")
            if isinstance(ts, (int, float)):
                if ts < WINDOW_START or (WINDOW_END and ts > WINDOW_END):
                    out_of_window += 1

            if r.get("has_reply") == 1:
                replied += 1

            d = r.get("reply_delay_days")
            if isinstance(d, (int, float)) and d >= 0:
                delays.append(d)

    return {
        "records": n,
        "unique_tid": len(tids),
        "dup_tid": dup,
        "date_min": min(dates) if dates else None,
        "date_max": max(dates) if dates else None,
        "out_of_window": out_of_window,
        "by_board": dict(sorted(by_board.items(), key=lambda x: -x[1])),
        "missing": dict(missing),
        "replied": replied,
        "reply_rate_pct": round(replied / n * 100, 2) if n else 0.0,
        "delay_median": round(statistics.median(delays), 2) if delays else None,
        "delay_mean": round(statistics.mean(delays), 2) if delays else None,
    }


def main():
    ap = argparse.ArgumentParser(description="数据集核验")
    ap.add_argument("--input", default=DEFAULT_INPUT, help="collected_*.jsonl 路径")
    ap.add_argument("--baseline", default=DEFAULT_BASELINE, help="基线 JSON 路径")
    ap.add_argument("--write-baseline", action="store_true",
                    help="以当前输入生成/覆盖基线文件")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"[x] 找不到数据文件: {args.input}")
        print("    把 collected_all13_20260914.jsonl 放到仓库根目录, 或用 --input 指定路径。")
        return 2

    digest, size = sha256_and_size(args.input)
    m = collect_metrics(args.input)
    m["sha256"] = digest
    m["bytes"] = size
    m["file"] = os.path.basename(args.input)

    if args.write_baseline:
        with open(args.baseline, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=2, sort_keys=True)
        print(f"[√] 基线已写入 {args.baseline}")
        print(f"    条数={m['records']}  唯一tid={m['unique_tid']}  sha256={digest[:16]}...")
        return 0

    if not os.path.exists(args.baseline):
        print(f"[x] 找不到基线文件: {args.baseline}")
        return 2

    with open(args.baseline, encoding="utf-8") as f:
        base = json.load(f)

    checks = [
        ("文件哈希(前16位)", (base.get("sha256") or "")[:16], digest[:16]),
        ("字节数", base.get("bytes"), size),
        ("总条数", base.get("records"), m["records"]),
        ("唯一 tid 数", base.get("unique_tid"), m["unique_tid"]),
        ("重复 tid 数", base.get("dup_tid"), m["dup_tid"]),
        ("最早留言时间", base.get("date_min"), m["date_min"]),
        ("最晚留言时间", base.get("date_max"), m["date_max"]),
        ("窗外条数(应为 0)", base.get("out_of_window"), m["out_of_window"]),
        ("有回复条数", base.get("replied"), m["replied"]),
        ("回复率(%)", base.get("reply_rate_pct"), m["reply_rate_pct"]),
        ("回复时延中位数(天)", base.get("delay_median"), m["delay_median"]),
    ]

    print("=" * 62)
    print("数据集核验报告")
    print("=" * 62)
    print(f"文件: {m['file']}  ({size / 1024 / 1024:.1f} MB)")
    print(f"SHA-256: {digest}")
    print("-" * 62)
    print(f"{'检查项':<22}{'基线':<20}{'实际':<20}{'结论'}")
    print("-" * 62)

    failed = 0
    for name, exp, act in checks:
        ok = (exp == act)
        if not ok:
            failed += 1
        print(f"{name:<22}{str(exp):<20}{str(act):<20}{'OK' if ok else 'MISMATCH'}")

    print("-" * 62)
    b_board = base.get("by_board", {})
    a_board = m["by_board"]
    board_ok = (b_board == a_board)
    print(f"{'板块分布':<22}{len(b_board)} 个板块{'':<8}{len(a_board)} 个板块{'':<8}"
          f"{'OK' if board_ok else 'MISMATCH'}")
    if not board_ok:
        failed += 1
        for k in sorted(set(b_board) | set(a_board)):
            if b_board.get(k) != a_board.get(k):
                print(f"    {k}: 基线={b_board.get(k)} 实际={a_board.get(k)}")

    b_miss = base.get("missing", {})
    miss_ok = (b_miss == m["missing"])
    print(f"{'字段缺失计数':<22}{'—':<20}{'—':<20}{'OK' if miss_ok else 'MISMATCH'}")
    if not miss_ok:
        failed += 1
        for k in sorted(set(b_miss) | set(m["missing"])):
            if b_miss.get(k) != m["missing"].get(k):
                print(f"    {k}: 基线={b_miss.get(k)} 实际={m['missing'].get(k)}")

    print("=" * 62)
    if failed == 0:
        print("结论: 全部通过 —— 该文件与产出分析结果的数据集完全一致。")
        return 0
    print(f"结论: {failed} 项不一致 —— 请核对文件是否被改动或替换。")
    return 1


if __name__ == "__main__":
    sys.exit(main())

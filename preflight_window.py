#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
采集前预检（零网络、零写入）
================================================================
只做三件事：
  1) 用 config 的时间窗过滤 13 个板块的列表缓存，逐板块报命中条数；
  2) 确认新输出文件为空（= 全量重采，不会跳过任何 tid）；
  3) 估算全量重采耗时。
不改任何数据文件，不发任何请求。
用法: python preflight_window.py
"""
import json, os, sys, time, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import config as CFG


def ts(t):
    if not t:
        return "-"
    return time.strftime("%Y-%m-%d", time.localtime(int(t)))


def main():
    print("=" * 68)
    print("  采集前预检 (零网络)")
    print("=" * 68)
    print(f"目标板块 : {len(CFG.FIDS)} 个")
    print(f"时间窗   : {ts(CFG.WINDOW_START_TS)} ~ "
          f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(CFG.WINDOW_END_TS))}")
    print(f"输出文件 : {CFG.OUT_NAME}")
    print()

    # ---- 1) 窗口过滤 ----
    print(f"{'板块':<14}{'fid':>6}{'缓存':>7}{'窗内':>7}{'窗外':>7}   {'窗内最早':<11}{'窗内最新'}")
    print("-" * 68)
    grand_in = grand_out = grand_cache = 0
    per_board = {}
    for fid, fname in CFG.FIDS:
        p = os.path.join(HERE, f"list_{fid}.json")
        if not os.path.exists(p):
            print(f"{fname:<14}{fid:>6}   无缓存  <<< 需要联网抓列表")
            continue
        items = json.load(open(p, encoding="utf-8"))
        inw = [it for it in items
               if int(it.get("createDateline") or 0) >= CFG.WINDOW_START_TS
               and int(it.get("createDateline") or 0) <= CFG.WINDOW_END_TS]
        out = len(items) - len(inw)
        ds = sorted(int(it.get("createDateline") or 0) for it in inw)
        grand_cache += len(items)
        grand_in += len(inw)
        grand_out += out
        per_board[fid] = len(inw)
        print(f"{fname:<14}{fid:>6}{len(items):>7}{len(inw):>7}{out:>7}   "
              f"{ts(ds[0]) if ds else '-':<11}{ts(ds[-1]) if ds else '-'}")
    print("-" * 68)
    print(f"{'合计':<14}{'':>6}{grand_cache:>7}{grand_in:>7}{grand_out:>7}")
    print()

    # ---- 2) 输出文件状态 ----
    if os.path.exists(CFG.OUT):
        n = sum(1 for l in open(CFG.OUT, encoding="utf-8") if l.strip())
        print(f"[输出文件] 已存在，含 {n} 条 -> 只会补采缺失的 {grand_in - n} 条（不是全量重采）")
    else:
        print(f"[输出文件] 不存在 -> 13 板块全部 {grand_in} 条都会重新采集（统一快照）")
    print()

    # ---- 3) 耗时估算 ----
    det = sum(CFG.DETAIL_INTERVAL) / 2
    detail_sec = grand_in * det
    cool_sec = (grand_in // CFG.COOLDOWN_EVERY) * CFG.COOLDOWN_SEC
    total = detail_sec + cool_sec
    eta = datetime.datetime.now() + datetime.timedelta(seconds=total)
    print(f"[耗时估算] 详情 {grand_in} 条 x {det:.2f}s + "
          f"{grand_in // CFG.COOLDOWN_EVERY} 次冷却 x {CFG.COOLDOWN_SEC}s")
    print(f"           = {total / 3600:.1f} 小时，若现在开跑，约 {eta.strftime('%m-%d %H:%M')} 完成")
    print()
    print("=" * 68)
    print(f"  预检结论: 窗口内应采 {grand_in} 条（窗外 {grand_out} 条已跳过，不发请求）")
    print("=" * 68)

    # 落盘一份预检摘要，便于事后核对
    summary = {
        "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "window_start": CFG.WINDOW_START_TS,
        "window_end": CFG.WINDOW_END_TS,
        "window_readable": [ts(CFG.WINDOW_START_TS),
                            time.strftime("%Y-%m-%d", time.localtime(CFG.WINDOW_END_TS))],
        "out_name": CFG.OUT_NAME,
        "cached_total": grand_cache,
        "in_window": grand_in,
        "out_window": grand_out,
        "per_board_in_window": {str(fid): per_board[fid] for fid, _ in CFG.FIDS},
        "eta_hours": round(total / 3600, 2),
    }
    json.dump(summary, open(os.path.join(HERE, "preflight_20260914.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("摘要已写入 preflight_20260914.json")


if __name__ == "__main__":
    main()

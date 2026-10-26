#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
可采集时间范围探测 —— 只读，不抓正文
================================================================
目的：查清"现在"（2026-09-14）13 个板块各自能翻到的最早/最新日期与条数，
      用来更新论文的时间窗表述，并估算剩余采集量。

与 count_all.py 的区别（重要）：
  count_all.py 调列表接口时漏传了 showUnAnswer，会漏掉"待回复/办理中"留言，
  实测因此少算约 20%（1217+1218 少算 678 条）。本脚本显式传 showUnAnswer=1，
  得到的条数与主采集程序一致。

安全约定：
  - 只调 /v1/threads/list/df，不调详情接口，不写任何采集结果
  - 列表节奏沿用实测安全值：9s ± 1s 抖动，每 10 次额外冷却 30s
  - 不修改 config.py / collected_*.jsonl / results/
  - 旧的 list_*.json 先备份到 backup_pre_probe/，再写入刷新版
  - 全量结果写入 window_probe_<日期>.json，每页落盘，可断点续跑
================================================================
"""
import os, sys, json, time, random, shutil, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config as CFG
import scraper_collect as SC

PROBE_JSON = os.path.join(HERE, f"window_probe_{time.strftime('%Y%m%d')}.json")
BACKUP_DIR = os.path.join(HERE, "backup_pre_probe")
EXTRA_COOLDOWN_EVERY = 10      # 每 10 次列表请求额外冷却
EXTRA_COOLDOWN_SEC = 30
LIST_INTERVAL = CFG.LIST_INTERVAL
TIME_BUDGET_SEC = 45 * 60      # 总时长安全阀: 超过则停止并保存已有进度

START_TS = time.time()
BUDGET_HIT = [False]


def over_budget():
    if time.time() - START_TS > TIME_BUDGET_SEC:
        BUDGET_HIT[0] = True
        return True
    return False


def fmt(ts):
    if not ts:
        return None
    return time.strftime("%Y-%m-%d", time.localtime(int(ts)))


def load_progress():
    if os.path.exists(PROBE_JSON):
        try:
            return json.load(open(PROBE_JSON, encoding="utf-8"))
        except Exception:
            pass
    return {"probed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "note": "列表接口只读探测, showUnAnswer=1", "boards": {}, "request_count": 0}


def save(data):
    json.dump(data, open(PROBE_JSON, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


def backup_existing(fid):
    """旧 list_<fid>.json 备份一次, 不重复备份"""
    src = os.path.join(HERE, f"list_{fid}.json")
    if not os.path.exists(src):
        return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    dst = os.path.join(BACKUP_DIR, f"list_{fid}.json")
    if not os.path.exists(dst):
        shutil.copy2(src, dst)


def probe_board(fid, name, data, req_counter):
    """游标翻页到底, 返回 (items, pages, rate_limited)"""
    items = []
    last = ""
    page = 0
    empty_streak = 0
    while True:
        if over_budget():
            print(f"  [安全阀] 已用满 {TIME_BUDGET_SEC // 60} 分钟预算, {name} 中断 (进度已存)", flush=True)
            return items, page, True
        page += 1
        param = {"fid": str(fid),
                 "showUnAnswer": 1,
                 "lastItem": last,
                 "position": 0,
                 "rows": 200,
                 "orderType": 2}
        try:
            d = SC.call_with_retry("/v1/threads/list/df", param, label=f"probe {fid} p{page}")
        except Exception as e:
            print(f"  [放弃] {name} 第{page}页: {e}", flush=True)
            return items, page, True

        req_counter[0] += 1
        data["request_count"] = req_counter[0]
        if req_counter[0] % EXTRA_COOLDOWN_EVERY == 0:
            print(f"  [节奏] 已发 {req_counter[0]} 次列表请求, 额外冷却 {EXTRA_COOLDOWN_SEC}s ...", flush=True)
            time.sleep(EXTRA_COOLDOWN_SEC)

        rd = d.get("resultData") or {}
        arr = rd.get("data") or []
        has_data = rd.get("hasData", 1)
        if not arr:
            empty_streak += 1
            if empty_streak >= 2 or has_data == 0:
                print(f"  [列表] {name} 第{page}页为空, 结束 (共 {len(items)} 条)", flush=True)
                break
            time.sleep(LIST_INTERVAL + random.uniform(0, 2))
            continue

        empty_streak = 0
        items.extend(arr)
        oldest = min((i.get("createDateline") or 0) for i in arr)
        print(f"  [列表] {name} 第{page}页 +{len(arr)} => 累计 {len(items)} (本页最早 {fmt(oldest)})", flush=True)
        last = str(arr[-1].get("tid", ""))
        time.sleep(LIST_INTERVAL + random.uniform(-1, 1))
    return items, page, False


def main():
    data = load_progress()
    req_counter = [data.get("request_count", 0)]

    print("=" * 68)
    print(" 可采集时间范围探测 (只读)")
    print(f" 开始: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f" 目标: {len(CFG.ALL_FIDS)} 个板块 | 节奏: 列表 {LIST_INTERVAL}s±1s, "
          f"每 {EXTRA_COOLDOWN_EVERY} 次冷却 {EXTRA_COOLDOWN_SEC}s")
    print(f" 结果: {PROBE_JSON}")
    print("=" * 68)

    for fid, name in CFG.ALL_FIDS:
        if BUDGET_HIT[0]:
            print(f"\n[安全阀] 预算耗尽, 跳过剩余板块 (重跑本脚本可续)", flush=True)
            break
        key = str(fid)
        done = data["boards"].get(key)
        if done and done.get("items"):
            print(f"\n===== {name}({fid}) 已有探测结果 {done['total']} 条, 跳过 =====", flush=True)
            continue

        print(f"\n===== 探测 {name}(fid={fid}) =====", flush=True)
        items, pages, rl = probe_board(fid, name, data, req_counter)

        if not items:
            print(f"  [警告] {name} 未取到任何数据, 记录后继续", flush=True)
            data["boards"][key] = {"fid": fid, "name": name, "total": 0,
                                   "done": False, "pages": pages}
            save(data)
            continue

        ts_list = [i.get("createDateline") or 0 for i in items]
        data["boards"][key] = {
            "fid": fid, "name": name,
            "total": len(items),
            "unique_tid": len(set(str(i.get("tid")) for i in items)),
            "earliest_ts": min(ts_list),
            "earliest_date": fmt(min(ts_list)),
            "latest_ts": max(ts_list),
            "latest_date": fmt(max(ts_list)),
            "pages": pages,
            "rate_limited": rl,
            "done": not rl,
            "items": items,          # 完整列表, 可直接当 list_<fid>.json 用
        }
        save(data)

        # 刷新 list 缓存(旧文件先备份), 让后续正式采集跳过列表阶段
        backup_existing(fid)
        json.dump(items, open(os.path.join(HERE, f"list_{fid}.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)

        print(f"  [完成] {name}: {len(items)} 条 | 最早 {fmt(min(ts_list))} | 最新 {fmt(max(ts_list))}", flush=True)

    # ---------- 汇总 ----------
    print("\n" + "=" * 68)
    print(" 汇总")
    print("=" * 68)
    total_all = 0
    earliest_all = None
    for fid, name in CFG.ALL_FIDS:
        b = data["boards"].get(str(fid))
        if not b:
            continue
        total_all += b["total"]
        e = b.get("earliest_date")
        if e and (earliest_all is None or e < earliest_all):
            earliest_all = e
        print(f"  {name:<12}({fid})  {b['total']:>5} 条 | {e} ~ {b.get('latest_date')}"
              + ("  [限流中断]" if b.get("rate_limited") else ""))
    data["summary"] = {"probed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "boards_probed": len(data["boards"]),
                       "total_all_boards": total_all,
                       "earliest_all_boards": earliest_all,
                       "request_count": req_counter[0]}
    save(data)
    print(f"\n  13 板块合计: {total_all} 条 | 全局最早: {earliest_all}")
    print(f"  列表请求总数: {req_counter[0]} | 结果文件: {PROBE_JSON}")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())

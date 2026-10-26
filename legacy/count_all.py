#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""广州市留言板可采集总量计数 v2(全类型 + 保守节奏 + 403 退避 + 断点续跑)。
- 列表接口 /v1/threads/list/df, rows=200, 游标 lastItem
- 列表请求间隔 9s(±2s 抖动) —— 注意: 原定 3.5s 实测会触发 403 限流, 已放慢
- 403 时指数退避 30/60/120/240/480s; 仍失败则标记该板块 rate_limited 并跳到下一个(可重跑续)
- 每成功 10 次额外冷却 20s
- 统计: 总返回条数 / 近两年(>=2024-08-19) / 开题窗(2021-01-01~2025-12-31) / 最早日期
- 只计数不存正文
"""
import urllib.request, json, hashlib, time, datetime, os, random, sys

# ==================== 读取集中配置 config.py(换机只需改它) ====================
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
try:
    import config as CFG
    SECRET = CFG.get_secret()
    APPCODE = CFG.APPCODE
    UA = CFG.UA
    BASE = CFG.BASE
    SUBFORUMS = list(CFG.ALL_FIDS)
    LIST_INTERVAL = CFG.LIST_INTERVAL
except ImportError:
    SECRET = os.environ.get("LIUYAN_SECRET", "").strip()
    if not SECRET:
        raise SystemExit("[x] 缺少 config.py 且未设置环境变量 LIUYAN_SECRET。")
    APPCODE = "PC42ce3bfa4980a9"
    UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    BASE = "https://liuyan.people.com.cn"
    SUBFORUMS = [
        (1217, "广州市委书记"), (1218, "广州市市长"),
        (2813, "越秀区"), (2814, "荔湾区"), (2815, "海珠区"), (2816, "天河区"),
        (2817, "白云区"), (2818, "黄埔区"), (2819, "番禺区"), (2820, "花都区"),
        (2821, "南沙区"), (2823, "增城区"), (2824, "从化区"),
    ]
    LIST_INTERVAL = 9.0

# 输出(相对本脚本目录, 换机无需修改)
OUT = os.path.join(HERE, "count_result.json")

TS_2YR = int(datetime.datetime(2024, 8, 19).timestamp())
TS_WIN_START = int(datetime.datetime(2021, 1, 1).timestamp())
TS_WIN_END = int(datetime.datetime(2025, 12, 31, 23, 59, 59).timestamp())
BACKOFF = [30, 60, 120, 240, 480]

def sign(path, param, token=""):
    s = path + json.dumps(param, separators=(',', ':'), ensure_ascii=False) + SECRET + token
    return hashlib.md5(s.encode('utf-8')).hexdigest()

def raw_call(path, param, token=""):
    body = {"appCode": APPCODE, "token": token, "signature": sign(path, param, token),
            "param": json.dumps(param, separators=(',', ':'), ensure_ascii=False)}
    headers = {"Content-Type": "application/json", "User-Agent": UA,
               "Referer": BASE + "/pro-dfbbs-front/threads/list?fid=1217"}
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers=headers)
    return json.loads(urllib.request.urlopen(req, timeout=30).read())

def safe_call(path, param, token=""):
    for wait in [0] + BACKOFF:
        if wait:
            print(f"    [403退避] 等待 {wait}s ...", flush=True)
            time.sleep(wait)
        try:
            return raw_call(path, param, token)
        except urllib.error.HTTPError as e:
            if e.code == 403:
                continue
            raise
    raise RuntimeError("持续 403, 放弃该板块")

def load_progress():
    if os.path.exists(OUT):
        try:
            return json.load(open(OUT, encoding="utf-8"))
        except Exception:
            pass
    return {"subforums": {}}

def save_progress(data):
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

def main():
    data = load_progress()
    data.setdefault("subforums", {})
    data["meta"] = {
        "ts_2yr_threshold": TS_2YR, "two_year_threshold_str": "2024-08-19",
        "ts_window_start": TS_WIN_START, "ts_window_end": TS_WIN_END,
        "thesis_window_str": "2021-01-01 ~ 2025-12-31",
        "rows_per_page": 200, "list_interval_sec": LIST_INTERVAL,
        "note": "去掉 typeId 类型过滤, 数全部类型; 原 3.5s 实测触发 403, 改为 9s",
        "run_started": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    req_count = 0
    for fid, name in SUBFORUMS:
        key = f"{fid}_{name}"
        rec = data["subforums"].get(key, {})
        if rec.get("done"):
            print(f"[skip] {name} 已完成(总={rec.get('total_retrieved')})", flush=True)
            continue
        if rec.get("rate_limited"):
            print(f"[skip] {name} 上次被限流, 本次重试", flush=True)
        print(f"\n===== 计数 {name}(fid={fid}) =====", flush=True)
        total = rec.get("total", 0)
        within_2yr = rec.get("within_2yr", 0)
        within_thesis = rec.get("within_thesis_window", 0)
        earliest_ts = rec.get("earliest_ts")
        earliest_info = rec.get("earliest_example")
        last_item = rec.get("last_item", "")
        page = rec.get("pages", 0)
        empty_streak = 0
        while True:
            page += 1
            try:
                d = safe_call("/v1/threads/list/df",
                              {"fid": str(fid), "lastItem": str(last_item), "position": 0,
                               "rows": 200, "orderType": 2})
            except RuntimeError:
                rec.update({"fid": fid, "name": name, "rate_limited": True,
                            "total": total, "within_2yr": within_2yr,
                            "within_thesis_window": within_thesis, "earliest_ts": earliest_ts,
                            "earliest_example": earliest_info, "last_item": last_item, "pages": page})
                data["subforums"][key] = rec
                save_progress(data)
                print(f"  [限流跳过] {name}: 已得 {total} 条, 下次重跑续", flush=True)
                break
            req_count += 1
            arr = d.get("resultData", {}).get("data", [])
            has_data = d.get("resultData", {}).get("hasData", 0)
            if not arr:
                empty_streak += 1
                if empty_streak >= 2 or has_data == 0:
                    print(f"  >> 数据耗尽(空{empty_streak}/hasData={has_data})", flush=True)
                    break
                time.sleep(LIST_INTERVAL + random.uniform(0, 2))
                continue
            empty_streak = 0
            total += len(arr)
            for it in arr:
                ts = it.get("createDateline") or it.get("dateline") or 0
                if ts:
                    if earliest_ts is None or ts < earliest_ts:
                        earliest_ts = ts
                        earliest_info = {"tid": it.get("tid"), "subject": it.get("subject"),
                                         "date": datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")}
                    if ts >= TS_2YR:
                        within_2yr += 1
                    if TS_WIN_START <= ts <= TS_WIN_END:
                        within_thesis += 1
            last_item = str(arr[-1].get("tid", ""))
            if page % 5 == 0:
                print(f"  {name}: {page}页/{total}条/最早{datetime.datetime.fromtimestamp(earliest_ts).strftime('%Y-%m-%d') if earliest_ts else '?'}", flush=True)
            # 每 10 次请求额外冷却, 防限流
            if req_count % 10 == 0:
                print(f"    [节奏] 已{req_count}次请求, 额外冷却20s", flush=True)
                time.sleep(20)
            time.sleep(LIST_INTERVAL + random.uniform(0, 2))
        else:
            pass
        if not rec.get("rate_limited"):
            rec = {"fid": fid, "name": name, "done": True, "total": total,
                   "within_2yr": within_2yr, "within_thesis_window": within_thesis,
                   "earliest_ts": earliest_ts,
                   "earliest_date": datetime.datetime.fromtimestamp(earliest_ts).strftime("%Y-%m-%d") if earliest_ts else None,
                   "earliest_example": earliest_info, "pages": page}
            data["subforums"][key] = rec
            save_progress(data)
            print(f"  [完成] {name}: 总={total} 近两年={within_2yr} 开题窗={within_thesis} 最早={rec['earliest_date']}", flush=True)
    subs = data["subforums"]
    tot = sum(r.get("total_retrieved", r.get("total", 0)) for r in subs.values())
    t2 = sum(r.get("within_2yr", 0) for r in subs.values())
    tw = sum(r.get("within_thesis_window", 0) for r in subs.values())
    data["summary"] = {"grand_total_retrieved": tot, "grand_within_2yr": t2,
                       "grand_within_thesis_window": tw, "subforum_count": len([r for r in subs.values() if r.get("done")]),
                       "run_finished": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    save_progress(data)
    print("\n########## 汇总 ##########", flush=True)
    print(f"可采集总量(接口返回到尽头): {tot}", flush=True)
    print(f"  近两年(>=2024-08-19): {t2}", flush=True)
    print(f"  开题窗(2021-01-01~2025-12-31): {tw}", flush=True)

if __name__ == "__main__":
    main()

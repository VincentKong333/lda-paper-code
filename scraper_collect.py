#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
人民网领导留言板 广州市 · 市委书记(1217) + 市长(1218) 正文采集
- 列表接口: POST /v1/threads/list/df  (游标分页, 仅取元数据+tid)
- 详情接口: POST /v1/threads/content  (取留言正文 + 官方回复)
- 签名: md5(接口path + JSON(param) + SECRET + token)
- 反爬: 列表请求间隔 9s; 详情请求间隔 4.5~6s; 403 指数退避; 每 50 次额外冷却
- 断点续跑: 已写入 collected.jsonl 的 tid 跳过; 列表页游标进度落盘
输出: collected_1217_1218.jsonl (每行一条 JSON 记录)
"""
import urllib.request, json, hashlib, time, os, random, sys

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
    FIDS = list(CFG.FIDS)
    _LP = dict(CFG.LIST_PARAM)
    WINDOW_START_TS = CFG.WINDOW_START_TS
    WINDOW_END_TS = CFG.WINDOW_END_TS
    LIST_INTERVAL = CFG.LIST_INTERVAL
    DETAIL_INTERVAL = CFG.DETAIL_INTERVAL
    COOLDOWN_EVERY = CFG.COOLDOWN_EVERY
    COOLDOWN_SEC = CFG.COOLDOWN_SEC
    BACKOFF = list(CFG.BACKOFF)
    MAX_RETRY = CFG.MAX_RETRY
    OUT = CFG.OUT
    LIST_CACHE = {fid: os.path.join(HERE, f"list_{fid}.json") for fid, _ in FIDS}
except ImportError:
    # ---- 兜底默认值: 缺少 config.py 时仍可独立运行 ----
    _LP = {"showUnAnswer": 1, "position": 0, "rows": 200, "orderType": 2}
    SECRET = os.environ.get("LIUYAN_SECRET", "").strip()
    if not SECRET:
        raise SystemExit("[x] 缺少 config.py 且未设置环境变量 LIUYAN_SECRET。")
    APPCODE = "PC42ce3bfa4980a9"
    UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    BASE = "https://liuyan.people.com.cn"
    FIDS = [(1217, "广州市委书记"), (1218, "广州市市长")]
    WINDOW_START_TS = 0
    WINDOW_END_TS = None
    LIST_INTERVAL = 9.0
    DETAIL_INTERVAL = (4.5, 6.0)
    COOLDOWN_EVERY = 40
    COOLDOWN_SEC = 30
    BACKOFF = [30, 60, 120, 240, 300, 420, 600, 600, 600, 600]
    MAX_RETRY = 40
    OUT = os.path.join(HERE, "collected_1217_1218.jsonl")
    LIST_CACHE = {fid: os.path.join(HERE, f"list_{fid}.json") for fid, _ in FIDS}

def ts2date(ts):
    if not ts: return None
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(ts)))

def sign(path, param, token=""):
    return hashlib.md5((path + json.dumps(param, separators=(',',':'), ensure_ascii=False) + SECRET + token).encode()).hexdigest()

def call(path, param, token="", referer="https://liuyan.people.com.cn/"):
    body = {"appCode": APPCODE, "token": token, "signature": sign(path, param, token),
            "param": json.dumps(param, separators=(',',':'), ensure_ascii=False)}
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": UA, "Referer": referer})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())

def call_with_retry(path, param, label="", referer="https://liuyan.people.com.cn/"):
    i = 0
    while i < MAX_RETRY:
        try:
            return call(path, param, referer=referer)
        except urllib.error.HTTPError as e:
            if e.code == 403:
                wait = BACKOFF[min(i, len(BACKOFF) - 1)]
                print(f"  [403] {label} 退避 {wait}s (第{i+1}/{MAX_RETRY}次)", flush=True)
                time.sleep(wait)
                i += 1
            else:
                raise
        except Exception as e:
            wait = BACKOFF[min(i, len(BACKOFF) - 1)]
            print(f"  [ERR] {label} {e} 重试等待 {wait}s (第{i+1}/{MAX_RETRY}次)", flush=True)
            time.sleep(wait)
            i += 1
    raise RuntimeError(f"放弃请求 {label} (连续 {MAX_RETRY} 次失败)")

def load_list_cache(fid):
    p = LIST_CACHE[fid]
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            return []
    return []

def save_list_cache(fid, items):
    json.dump(items, open(LIST_CACHE[fid], "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def crawl_list(fid, fname):
    """游标翻页收集该板块全部列表项(元数据+tid), 落盘缓存。返回 list of items。"""
    items = load_list_cache(fid)
    if items:
        print(f"[列表] {fname}({fid}) 已缓存 {len(items)} 条, 跳过", flush=True)
        return items
    print(f"[列表] 开始爬 {fname}({fid}) ...", flush=True)
    last = ""
    page = 0
    while True:
        page += 1
        # 参数键顺序与线上保持一致(fid, showUnAnswer, lastItem, position, rows, orderType)
        param = {"fid": str(fid),
                 "showUnAnswer": _LP.get("showUnAnswer", 1),
                 "lastItem": last,
                 "position": _LP.get("position", 0),
                 "rows": _LP.get("rows", 200),
                 "orderType": _LP.get("orderType", 2)}
        d = call_with_retry("/v1/threads/list/df", param, label=f"list {fid} p{page}")
        arr = d.get("resultData", {}).get("data", [])
        if not arr:
            print(f"  [列表] {fname} 第{page}页为空, 结束 (共 {len(items)} 条)", flush=True)
            break
        items.extend(arr)
        save_list_cache(fid, items)
        print(f"  [列表] {fname} 第{page}页 +{len(arr)} => 累计 {len(items)} (最早 {ts2date(arr[-1].get('createDateline'))})", flush=True)
        last = str(arr[-1].get("tid", ""))
        time.sleep(LIST_INTERVAL + random.uniform(-1, 1))
    return items

def reply_dept_level(organization):
    """市级板块回复部门层级推断: 含'区'->2, 含'镇/街道'->3, 否则 1(市级/省级)"""
    if not organization:
        return None
    if "镇" in organization or "街道" in organization:
        return 3
    if "区" in organization:
        return 2
    return 1

def build_record(item, detail):
    rd = detail.get("resultData", {})
    cl = rd.get("contentList", [])
    # 留言主体: dataType==1 (通常 contentList[0])
    msg = next((c for c in cl if c.get("dataType") == 1), cl[0] if cl else {})
    # 官方回复: dataType==4
    replies = [c for c in cl if c.get("dataType") == 4]
    reply = replies[0] if replies else {}
    create_ts = int(msg.get("createDateline") or item.get("createDateline") or 0)
    reply_ts = int(reply.get("dateline") or 0)
    rec = {
        "tid": item.get("tid") or msg.get("objId"),
        "fid": fid if (fid := item.get("fid")) else msg.get("fid"),
        "forum_name": item.get("forumName") or msg.get("forumName"),
        "subject": item.get("subject") or msg.get("subject"),
        "type_name": item.get("typeName") or msg.get("typeName"),
        "domain_name": item.get("domainName") or msg.get("domainName"),
        "state_info": item.get("stateInfo") or msg.get("stateInfo"),
        "nick_name": item.get("nickName") or msg.get("nickName"),
        "create_dateline": create_ts,
        "create_date": ts2date(create_ts),
        "content": msg.get("content"),
        "satisfaction": msg.get("satisfaction"),
        "from": msg.get("from"),
        "ip_place": msg.get("ipPlace"),
        "reply_content": reply.get("content"),
        "reply_organization": reply.get("organization"),
        "reply_dateline": reply_ts,
        "reply_date": ts2date(reply_ts),
        "reply_nick_name": reply.get("nickName"),
        "has_reply": 1 if replies else 0,
        "reply_delay_days": round((reply_ts - create_ts) / 86400, 3) if reply_ts and create_ts else None,
        "reply_dept_level": reply_dept_level(reply.get("organization")),
    }
    return rec

def main():
    collected_tids = set()
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    collected_tids.add(str(json.loads(line).get("tid")))
                except Exception:
                    pass
    print(f"[续跑] 已采集 {len(collected_tids)} 条, 将跳过", flush=True)

    out_f = open(OUT, "a", encoding="utf-8")
    total = 0
    detail_count = 0
    for fid, fname in FIDS:
        items = crawl_list(fid, fname)
        # 时间窗过滤
        items = [it for it in items
                 if (WINDOW_START_TS == 0 or int(it.get("createDateline", 0)) >= WINDOW_START_TS)
                 and (WINDOW_END_TS is None or int(it.get("createDateline", 0)) <= WINDOW_END_TS)]
        print(f"[详情] {fname} 待采集 {len(items)} 条 (已采 {sum(1 for it in items if str(it.get('tid')) in collected_tids)})", flush=True)
        for it in items:
            tid = str(it.get("tid"))
            if tid in collected_tids:
                continue
            d = call_with_retry("/v1/threads/content", {"tid": tid},
                                referer=f"https://liuyan.people.com.cn/threads/content?tid={tid}",
                                label=f"detail {tid}")
            rec = build_record(it, d)
            out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out_f.flush()
            collected_tids.add(tid)
            total += 1
            detail_count += 1
            if detail_count % COOLDOWN_EVERY == 0:
                print(f"  [进度] 已写 {total} 条, 冷却 {COOLDOWN_SEC}s ...", flush=True)
                time.sleep(COOLDOWN_SEC)
            time.sleep(random.uniform(*DETAIL_INTERVAL))
    out_f.close()
    print(f"\n[完成] 本次新增 {total} 条, 累计 {len(collected_tids)} 条 -> {OUT}", flush=True)

if __name__ == "__main__":
    main()

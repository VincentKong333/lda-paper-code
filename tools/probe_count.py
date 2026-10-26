#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探查列表接口响应结构:是否有总条数字段、rows 最大取值、forum info 接口字段。"""
import urllib.request, json, hashlib, time, os, sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import config as _CFG

SECRET = _CFG.get_secret()   # 从环境变量 LIUYAN_SECRET 读取, 不入库
APPCODE = "PC42ce3bfa4980a9"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
BASE = "https://liuyan.people.com.cn"

def sign(path, param, token=""):
    s = path + json.dumps(param, separators=(',', ':'), ensure_ascii=False) + SECRET + token
    return hashlib.md5(s.encode('utf-8')).hexdigest()

def call(path, param, token="", ref=None):
    body = {"appCode": APPCODE, "token": token, "signature": sign(path, param, token),
            "param": json.dumps(param, separators=(',', ':'), ensure_ascii=False)}
    headers = {"Content-Type": "application/json", "User-Agent": UA,
               "Referer": ref or (BASE + "/pro-dfbbs-front/threads/list?fid=1217")}
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers=headers)
    return json.loads(urllib.request.urlopen(req, timeout=30).read())

def keys_tree(d, depth=0, maxdepth=3):
    """打印字典/对象结构(不展开大数组)。"""
    pad = "  " * depth
    if isinstance(d, dict):
        for k, v in d.items():
            t = type(v).__name__
            if isinstance(v, list):
                print(f"{pad}{k}: list[{len(v)}]")
                if v and depth < maxdepth:
                    keys_tree(v[0], depth + 1, maxdepth)
            elif isinstance(v, dict):
                print(f"{pad}{k}: dict")
                if depth < maxdepth:
                    keys_tree(v, depth + 1, maxdepth)
            else:
                sv = str(v)
                print(f"{pad}{k}: {t} = {sv[:60]}")
    elif isinstance(d, list) and d:
        keys_tree(d[0], depth, maxdepth)

print("========== 1) 列表接口 /v1/threads/list/df 响应结构 (rows=20) ==========")
d = call("/v1/threads/list/df",
         {"fid": "1217", "showUnAnswer": 1, "typeId": 5, "lastItem": "", "position": 0, "rows": 20, "orderType": 2})
print("顶层 keys:", list(d.keys()))
print("resultData keys:", list(d.get("resultData", {}).keys()))
print("--- resultData 结构(含总数相关字段?) ---")
keys_tree(d.get("resultData", {}), 0, 2)
print("--- 是否有 total/count/hasNext/totalNum 等字段 ---")
rd = d.get("resultData", {})
for f in ("total", "totalNum", "count", "hasNext", "totalCount", "num", "size", "pages"):
    if f in rd:
        print(f"  >>> resultData.{f} = {rd[f]}")
arr = rd.get("data", [])
print("data 数组长度:", len(arr))
if arr:
    print("--- 单条 item 所有字段 ---")
    print(list(arr[0].keys()))
    print("--- 第一条(截断) ---")
    for k, v in arr[0].items():
        print(f"   {k}: {str(v)[:80]}")

print()
print("========== 2) 测试 rows 最大取值 (rows=100 / 200) ==========")
for r in (100, 200):
    t0 = time.time()
    dd = call("/v1/threads/list/df",
              {"fid": "1217", "showUnAnswer": 1, "typeId": 5, "lastItem": "", "position": 0, "rows": r, "orderType": 2})
    aa = dd.get("resultData", {}).get("data", [])
    print(f"  rows={r} -> 返回 {len(aa)} 条, 耗时 {time.time()-t0:.1f}s")

print()
print("========== 3) forum info 接口 /v1/forum/getForumInfos ==========")
fi = call("/v1/forum/getForumInfos", {"fid": "1217", "_t": int(time.time()*1000)},
          ref=BASE + "/pro-dfbbs-front/forum/list?fid=268")
print("顶层 keys:", list(fi.keys()))
print("resultData keys:", list(fi.get("resultData", {}).keys()))
keys_tree(fi.get("resultData", {}), 0, 3)

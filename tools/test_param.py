#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""冷却后诊断: 确认解封 + 确认"数全部类型"的正确参数。"""
import urllib.request, json, hashlib, time, datetime, os, sys
from collections import Counter

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

def call(path, param, token=""):
    body = {"appCode": APPCODE, "token": token, "signature": sign(path, param, token),
            "param": json.dumps(param, separators=(',', ':'), ensure_ascii=False)}
    # 用之前能成功的极简头部(不加 Origin,避免被 WAF 误判)
    headers = {"Content-Type": "application/json", "User-Agent": UA,
               "Referer": BASE + "/pro-dfbbs-front/threads/list?fid=1217"}
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers=headers)
    return json.loads(urllib.request.urlopen(req, timeout=30).read())

print("冷却 150s ...", flush=True)
time.sleep(150)

for label, param in [
    ("A: 无typeId, 无showUnAnswer", {"fid": "1217", "lastItem": "", "position": 0, "rows": 200, "orderType": 2}),
    ("B: 无typeId, showUnAnswer=0", {"fid": "1217", "showUnAnswer": 0, "lastItem": "", "position": 0, "rows": 200, "orderType": 2}),
]:
    try:
        d = call("/v1/threads/list/df", param)
        arr = d.get("resultData", {}).get("data", [])
        print(f"\n[{label}] OK 条数={len(arr)} hasData={d.get('resultData',{}).get('hasData')}")
        types = Counter()
        for it in arr:
            types[(it.get("typeName"), it.get("stateInfo"))] += 1
        print("  类型/状态分布:", dict(types.most_common(10)))
    except urllib.error.HTTPError as e:
        print(f"\n[{label}] HTTP {e.code} {e.reason}")
    except Exception as e:
        print(f"\n[{label}] ERR {repr(e)}")
    time.sleep(5)

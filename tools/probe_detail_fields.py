import urllib.request, json, hashlib, time, os, sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import config as _CFG

SECRET = _CFG.get_secret()   # 从环境变量 LIUYAN_SECRET 读取, 不入库
APPCODE = "PC42ce3bfa4980a9"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

def sign(path, param, token=""):
    return hashlib.md5((path + json.dumps(param, separators=(',',':'), ensure_ascii=False) + SECRET + token).encode()).hexdigest()

def call(path, param, token=""):
    body = {"appCode": APPCODE, "token": token, "signature": sign(path, param, token),
            "param": json.dumps(param, separators=(',',':'), ensure_ascii=False)}
    req = urllib.request.Request("https://liuyan.people.com.cn" + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": UA,
                 "Referer": "https://liuyan.people.com.cn/threads/content?tid=25686586"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())

# 测两个 tid: 一个已办理(25686586), 一个待回复(取列表里 stateInfo=待回复 的)
print("===== A. 已办理详情 tid=25686586 =====")
d = call("/v1/threads/content", {"tid": "25686586"})
print("top keys:", list(d.keys()))
rd = d.get("resultData", {})
print("resultData keys:", list(rd.keys()) if isinstance(rd, dict) else type(rd))
cl = rd.get("contentList", []) if isinstance(rd, dict) else []
print("contentList len:", len(cl))
for i, c in enumerate(cl):
    print(f"\n--- contentList[{i}] keys: {list(c.keys())} ---")
    for k, v in c.items():
        sv = str(v)
        print(f"   {k}: {sv[:140]}")

# 从列表拿一个 待回复 的 tid 来对比
print("\n\n===== B. 列表里找一个 待回复 的 tid =====")
lst = call("/v1/threads/list/df", {"fid": "1217", "showUnAnswer": 1, "lastItem": "", "position": 0, "rows": 50, "orderType": 2})
arr = lst.get("resultData", {}).get("data", [])
pending = next((x for x in arr if "待回复" in str(x.get("stateInfo", ""))), None)
print("pending found:", bool(pending), pending.get("tid") if pending else None, pending.get("stateInfo") if pending else None)
if pending:
    d2 = call("/v1/threads/content", {"tid": str(pending["tid"])})
    cl2 = d2.get("resultData", {}).get("contentList", [])
    print("pending contentList len:", len(cl2))
    for i, c in enumerate(cl2):
        print(f"--- pending contentList[{i}] keys: {list(c.keys())} ---")
        for k, v in c.items():
            print(f"   {k}: {str(v)[:140]}")

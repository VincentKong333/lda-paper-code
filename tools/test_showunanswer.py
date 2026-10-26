import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import scraper_collect as m
import json

def page(fid, show_unanswer, last=""):
    p = {"fid": str(fid), "lastItem": last, "position": 0, "rows": 200, "orderType": 2}
    if show_unanswer is not None:
        p["showUnAnswer"] = show_unanswer
    return m.call("/v1/threads/list/df", p)

# 第一页对比
a = page(1217, None)          # 不带 showUnAnswer
b = page(1217, 1)             # showUnAnswer=1
ca = a.get("resultData", {}).get("data", [])
cb = b.get("resultData", {}).get("data", [])
print("不带 showUnAnswer 第一页:", len(ca), "示例状态:", [x.get("stateInfo") for x in ca[:8]])
print("showUnAnswer=1  第一页:", len(cb), "示例状态:", [x.get("stateInfo") for x in cb[:8]])
# 待回复 数量对比
def cnt_pending(arr):
    return sum(1 for x in arr if "待回复" in str(x.get("stateInfo", "")))
print("不带 showUnAnswer 第一页 待回复数:", cnt_pending(ca))
print("showUnAnswer=1  第一页 待回复数:", cnt_pending(cb))
# tid 集合是否相同
ta = set(str(x.get("tid")) for x in ca)
tb = set(str(x.get("tid")) for x in cb)
print("第一页 tid 集合相同?", ta == tb, " 仅不带有的:", len(ta-tb), " 仅=1有的:", len(tb-ta))

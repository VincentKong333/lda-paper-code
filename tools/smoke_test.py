import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import scraper_collect as m
import json

# 1) 列表缓存(真实落盘, 全量板块 tid)
items = m.crawl_list(1217, "广州市委书记")
print("\n列表缓存条数:", len(items))
print("示例列表项 tid/subject/state:", items[0].get("tid"), items[0].get("subject"), items[0].get("stateInfo"))

# 2) 抽 3 条详情, 验证字段抽取
for it in items[:3]:
    tid = str(it.get("tid"))
    d = m.call_with_retry("/v1/threads/content", {"tid": tid},
                          referer=f"https://liuyan.people.com.cn/threads/content?tid={tid}",
                          label=f"detail {tid}")
    rec = m.build_record(it, d)
    print(f"\n=== tid={tid} ===")
    print(json.dumps(rec, ensure_ascii=False, indent=1))

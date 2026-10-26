import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import scraper_collect as m, json
# 已办理(有回复): 25686586 ; 待回复(无回复): 25965347
for tid in ["25686586", "25965347"]:
    # 从列表缓存找对应 item
    item = next((x for x in m.load_list_cache(1217) if str(x.get("tid")) == tid), {"tid": int(tid), "fid": 1217})
    d = m.call_with_retry("/v1/threads/content", {"tid": tid}, label=f"detail {tid}")
    rec = m.build_record(item, d)
    print(f"\n=== tid={tid} has_reply={rec['has_reply']} ===")
    print(json.dumps({k: (rec[k][:60]+'…' if isinstance(rec[k],str) and len(rec[k])>60 else rec[k]) for k in
                       ['tid','subject','state_info','domain_name','create_date','content','reply_organization','reply_date','reply_delay_days','has_reply','reply_dept_level','satisfaction']},
                      ensure_ascii=False, indent=1))

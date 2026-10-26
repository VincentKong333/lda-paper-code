#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
采集完成后的自动收尾监控器
================================================================
作用: 等待采集跑完, 然后自动
  1) 运行 analyze.py 生成《采集质量与分布报告.md》+《回复时延分布.csv》
  2) 把原始数据导出到 results/(jsonl 原样 + CSV 表格版)
  3) 写 results/DONE.txt 完成标记

判定"采集完成"的条件(任一满足):
  a) OUT 记录数 >= 目标数(目标 = 各板块 list_<fid>.json 条数之和)
  b) 采集进程已退出, 且输出文件连续 3 分钟无变化
  c) 输出文件连续 15 分钟无变化(疑似停滞)
  d) 超过 MAX_HOURS 小时(兜底)

启动方式(后台, 脱离终端):
  nohup python3 monitor_complete.py > monitor.log 2>&1 &
"""
import os, sys, time, json, subprocess, csv, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# ---- 读集中配置(缺失则用兜底值) ----
try:
    import config as CFG
    OUT = CFG.OUT
    RESULT_DIR = CFG.RESULT_DIR
    FIDS = list(CFG.FIDS)
except ImportError:
    OUT = os.path.join(HERE, "collected_1217_1218.jsonl")
    RESULT_DIR = os.path.join(HERE, "results")
    FIDS = [(1217, "广州市委书记"), (1218, "广州市市长")]

PY = sys.executable                      # 用当前解释器, 换机无需改路径
ANALYZE = os.path.join(HERE, "analyze.py")
REPORT = os.path.join(HERE, "采集质量与分布报告.md")
DELAY_CSV = os.path.join(HERE, "回复时延分布.csv")

POLL_SEC = 60          # 轮询间隔(秒)
MAX_HOURS = 12         # 最长等待小时数(兜底)
FALLBACK_FIELDS = ["tid", "fid", "forum_name", "subject", "type_name", "domain_name",
                   "state_info", "nick_name", "create_dateline", "create_date", "content",
                   "satisfaction", "from", "ip_place", "reply_content", "reply_organization",
                   "reply_dateline", "reply_date", "reply_nick_name", "has_reply",
                   "reply_delay_days", "reply_dept_level"]


def load_records():
    recs = []
    if not os.path.exists(OUT):
        return recs
    with open(OUT, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except Exception:
                pass
    return recs


def target_total():
    """目标总数 = 各板块列表缓存条数之和; 缓存不全则返回 None。"""
    total = 0
    for fid, _ in FIDS:
        p = os.path.join(HERE, f"list_{fid}.json")
        if not os.path.exists(p):
            return None
        try:
            total += len(json.load(open(p, encoding="utf-8")))
        except Exception:
            return None
    return total or None


def proc_alive():
    """是否有采集进程在跑(行尾锚定, 避免匹配到执行命令的 shell 自身)。"""
    try:
        out = subprocess.run(["pgrep", "-f", "scraper_collect\\.py$"],
                             capture_output=True, text=True)
        return bool(out.stdout.strip())
    except Exception:
        return False


def deliver_raw():
    """导出原始数据: jsonl 原样副本 + CSV 表格版(utf-8-sig, Excel 可直接打开)。"""
    os.makedirs(RESULT_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M")
    recs = load_records()
    n = len(recs)

    raw_jsonl = os.path.join(RESULT_DIR, f"原始数据_{ts}.jsonl")
    shutil.copyfile(OUT, raw_jsonl)

    fields = list(recs[0].keys()) if recs else FALLBACK_FIELDS
    raw_csv = os.path.join(RESULT_DIR, f"原始数据_{ts}.csv")
    with open(raw_csv, "w", newline="", encoding="utf-8-sig") as cf:
        w = csv.DictWriter(cf, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in recs:
            w.writerow({k: r.get(k, "") for k in fields})

    flag = os.path.join(RESULT_DIR, "DONE.txt")
    with open(flag, "w", encoding="utf-8") as ff:
        ff.write(f"采集完成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        ff.write(f"记录总数: {n} 条\n")
        ff.write(f"原始jsonl: {raw_jsonl}\n")
        ff.write(f"原始CSV:   {raw_csv}\n")
        ff.write(f"分析报告:  {REPORT}\n")
        ff.write(f"时延CSV:   {DELAY_CSV}\n")

    print(f"原始数据已导出:\n  {raw_jsonl}\n  {raw_csv}\n共 {n} 条", flush=True)
    return raw_jsonl, raw_csv


def main():
    tgt = target_total()
    print(f"monitor 启动 | 目标总数={tgt} | 输出={os.path.basename(OUT)}", flush=True)
    stable = 0
    last_sz = -1
    start = time.time()
    while True:
        n = len(load_records())
        sz = os.path.getsize(OUT) if os.path.exists(OUT) else 0
        stable = stable + 1 if sz == last_sz else 0
        last_sz = sz
        alive = proc_alive()
        tgt_str = f"/{tgt}" if tgt else ""
        print(f"  [{time.strftime('%H:%M:%S')}] 已采={n}{tgt_str}"
              f" 进程={'在' if alive else '无'} 文件稳定{stable}x{POLL_SEC}s", flush=True)

        if tgt and n >= tgt:
            print(f"已采满目标 {tgt} 条, 等 {POLL_SEC}s 稳妥后开始收尾 ...", flush=True)
            time.sleep(POLL_SEC)
            break
        if stable >= 15:
            print("文件连续 15 分钟无变化(疑似停滞), 基于现有数据收尾 ...", flush=True)
            break
        if (not alive) and stable >= 3:
            print("采集进程已退出且文件稳定, 开始收尾 ...", flush=True)
            break
        if time.time() - start > MAX_HOURS * 3600:
            print(f"等待超时({MAX_HOURS}h), 基于现有数据收尾 ...", flush=True)
            break
        time.sleep(POLL_SEC)

    print("运行 analyze.py ...", flush=True)
    r = subprocess.run([PY, ANALYZE], capture_output=True, text=True)
    print(r.stdout, flush=True)
    if r.returncode != 0:
        print("analyze 出错:\n" + (r.stderr or ""), flush=True)

    print("导出原始数据 ...", flush=True)
    try:
        deliver_raw()
    except Exception as e:
        print("deliver_raw 出错:", e, flush=True)
    print("MONITOR DONE", flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查看 data.jsonl / done.json 的统计信息,便于在爬虫跑的过程中查看进度"""

import json
from pathlib import Path
from collections import Counter
from datetime import datetime

OUT = Path(__file__).parent.resolve()
DATA = OUT / "data.jsonl"
DONE = OUT / "done.json"
LOG = OUT / "scraper.log"


def main():
    # done
    done_count = 0
    if DONE.exists():
        done_count = len(json.loads(DONE.read_text(encoding="utf-8")))

    # data
    n = 0
    leaders = Counter()
    statuses = Counter()
    topics = Counter()
    year_dist = Counter()
    by_year_leader = Counter()
    empty_text = 0
    empty_html = 0
    if DATA.exists():
        with DATA.open(encoding="utf-8") as f:
            for line in f:
                n += 1
                rec = json.loads(line)
                leaders[rec.get("leader", "?")] += 1
                statuses[rec.get("status_list") or "?"] += 1
                topics[rec.get("topic_list") or "?"] += 1
                t = (rec.get("time_list") or "")[:4]
                if t:
                    year_dist[t] += 1
                    by_year_leader[(t, rec.get("leader", "?"))] += 1
                if not rec.get("text_detail"):
                    empty_text += 1
                if not rec.get("html_detail"):
                    empty_html += 1

    print("=" * 60)
    print(f"完成集合(done.json): {done_count} 条")
    print(f"详情文件(data.jsonl): {n} 条")
    if n:
        print(f"  其中 text_detail 为空: {empty_text}")
        print(f"  其中 html_detail 为空: {empty_html}")
        print("\n-- 按板块 --")
        for k, v in sorted(leaders.items(), key=lambda x: -x[1]):
            print(f"  {k}: {v}")
        print("\n-- 按状态 --")
        for k, v in sorted(statuses.items(), key=lambda x: -x[1]):
            print(f"  {k}: {v}")
        print("\n-- 按年份 --")
        for k, v in sorted(year_dist.items()):
            print(f"  {k}: {v}")
        print("\n-- 按主题分类 --")
        for k, v in sorted(topics.items(), key=lambda x: -x[1]):
            print(f"  {k}: {v}")
    if LOG.exists():
        print("\n-- 最近 10 条日志 --")
        lines = LOG.read_text(encoding="utf-8").splitlines()
        for ln in lines[-10:]:
            print(f"  {ln}")


if __name__ == "__main__":
    main()
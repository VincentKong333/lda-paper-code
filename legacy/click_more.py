#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探测: 反复点'查看更多', 看列表是否能翻到 2021 (验证两年限制)"""

import re
import time
from datetime import date, datetime
from playwright.sync_api import sync_playwright

DATE_FLOOR = date(2024, 1, 1)  # 若触达 2024-01-01 之前, 说明远超两年
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
FID = 1217
CLICKS = int(__import__("sys").argv[1]) if len(__import__("sys").argv) > 1 else 25


def parse_date(s):
    if not s:
        return None
    s = re.sub(r"\s+", " ", s.strip())[:16]
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M").date()
    except ValueError:
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page()
    pg.goto(f"https://liuyan.people.com.cn/pro-dfbbs-front/threads/list?fid={FID}", wait_until="networkidle", timeout=60000)
    pg.wait_for_timeout(4000)

    for i in range(CLICKS):
        lis = pg.query_selector_all("ul.replyList li")
        earliest = None
        for li in lis:
            pe = li.query_selector(".headMainS p")
            if pe:
                d = parse_date(pe.inner_text())
                if d and (earliest is None or d < earliest):
                    earliest = d
        print(f"[{i+1}] li总数={len(lis)} 最早={earliest}")
        if earliest and earliest < DATE_FLOOR:
            print(">>> 已到 2024-01-01 之前, 远超近两年, 两年限制不成立")
            break
        btn = pg.locator("text=查看更多").last
        try:
            btn.click(timeout=8000)
        except Exception as e:
            print(f"点击查看更多失败(可能已到底): {e}")
            break
        pg.wait_for_timeout(2500)

    print("=" * 40)
    print("探测完成")
    b.close()
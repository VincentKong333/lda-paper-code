#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快速探针: 只翻列表页, 不抓详情, 验证时间窗边界(是否只能查近两年)"""

import re
import time
from datetime import date, datetime
from playwright.sync_api import sync_playwright

DATE_START = date(2021, 1, 1)
DATE_END = date(2025, 12, 31)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
FID = int(__import__("sys").argv[1]) if len(__import__("sys").argv) > 1 else 1217
MAX_PAGES = int(__import__("sys").argv[2]) if len(__import__("sys").argv) > 2 else 300


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
    pg.context.set_extra_http_headers({}) if False else None
    pg = b.new_context(user_agent=UA).new_page()
    pn = 1
    total = 0
    floor_hit = False
    while pn <= MAX_PAGES:
        url = f"https://liuyan.people.com.cn/pro-dfbbs-front/threads/list?fid={FID}&pageNumber={pn}"
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=30000)
            pg.wait_for_selector("ul.replyList li", timeout=15000)
        except Exception as e:
            print(f"p{pn}: 加载失败 {e}")
            break
        items = pg.evaluate(
            r"""() => Array.from(document.querySelectorAll('ul.replyList li')).map(li=>{
                const h2 = li.querySelector('h2');
                const t = h2 ? (h2.textContent.match(/留言ID:\s*\d+/), li.querySelector('.headMainS p')) : null;
                return li.querySelector('.headMainS p') ? li.querySelector('.headMainS p').textContent.replace(/ /g,' ').trim() : null;
            }).filter(Boolean)"""
        )
        if not items:
            print(f"p{pn}: 空页, 停止")
            break
        ds = [parse_date(x) for x in items if parse_date(x)]
        earliest = min(ds) if ds else None
        latest = max(ds) if ds else None
        total += len(items)
        print(f"p{pn}: {len(items)} 条 | 最早 {earliest} | 最新 {latest} | 累计 {total}")
        if earliest and earliest < DATE_START:
            print(f"  >>> 触达 {DATE_START} 之前, 平台列表仅近两年")
            floor_hit = True
            break
        pn += 1
        time.sleep(2.0)
    print("=" * 50)
    print(f"fid={FID}: 共翻 {pn} 页, 累计 {total} 条, 触底={floor_hit}, 最早 {earliest}")
    b.close()
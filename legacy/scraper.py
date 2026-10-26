#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
人民网领导留言板广州板块爬虫
- 列表页:遍历 13 个子板块 fid,翻页拿 tid + 基础字段(标题/时间/状态/主题/摘要)
- 详情页:访问 /threads/content?tid=xxx,抽 8 个标准字段
- 输出: data.jsonl(JSON Lines)
- 合规: 间隔 2-3 秒、User-Agent、仅公开页面、不登录
- 断点续爬: done.json

用法:
  python scraper.py               # 全量
  python scraper.py 1 1217        # 测试: 市委书记 1 页
  python scraper.py 20 1218       # 市长 20 页
"""

import json
import time
import re
import random
import sys
from pathlib import Path
from datetime import datetime, date
from playwright.sync_api import sync_playwright

# ============== 配置 ==============
BASE = "https://liuyan.people.com.cn"
LIST_URL = f"{BASE}/pro-dfbbs-front/threads/list"
DETAIL_URL = f"{BASE}/threads/content"
OUT_DIR = Path(__file__).parent.resolve()
DATA_FILE = OUT_DIR / "data.jsonl"
DONE_FILE = OUT_DIR / "done.json"
LOG_FILE = OUT_DIR / "scraper.log"

# 13 个子板块: (fid, 显示名, 层级)
FORUMS = [
    (1217, "广州市委书记", "市级"),
    (1218, "广州市市长", "市级"),
    (2813, "越秀区委书记", "区级"),
    (2814, "荔湾区委书记", "区级"),
    (2815, "海珠区委书记", "区级"),
    (2816, "天河区委书记", "区级"),
    (2817, "白云区委书记", "区级"),
    (2818, "黄埔区委书记", "区级"),
    (2819, "番禺区委书记", "区级"),
    (2820, "花都区委书记", "区级"),
    (2821, "南沙区委书记", "区级"),
    (2823, "增城区委书记", "区级"),
    (2824, "从化区委书记", "区级"),
]

# 研究目标时间窗(开题报告: 2021/1 - 2025/12)
DATE_START = date(2021, 1, 1)
DATE_END = date(2025, 12, 31)

# 间隔(秒, 报告合规要求)
SLEEP_LIST = (2.5, 4.0)
SLEEP_DETAIL = (2.0, 3.0)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

MAX_PAGES_PER_FORUM = int(sys.argv[1]) if len(sys.argv) > 1 else 9999
ONLY_FORUM = sys.argv[2] if len(sys.argv) > 2 else None


# ============== 工具 ==============
def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def sleep_jitter(lo_hi):
    time.sleep(random.uniform(*lo_hi))


def load_done():
    if DONE_FILE.exists():
        return set(json.loads(DONE_FILE.read_text(encoding="utf-8")))
    return set()


def save_done(s):
    DONE_FILE.write_text(json.dumps(sorted(s), ensure_ascii=False), encoding="utf-8")


def append_jsonl(obj):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with DATA_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


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


# ============== 列表页 ==============
def fetch_list_items(page, fid, page_num):
    url = f"{LIST_URL}?fid={fid}&pageNumber={page_num}"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        log(f"  列表页加载失败 fid={fid} p{page_num}: {e}")
        return []

    try:
        page.wait_for_selector("ul.replyList li", timeout=20000)
    except Exception:
        pass

    items = page.evaluate(
        r"""() => {
        const lis = Array.from(document.querySelectorAll('ul.replyList li'));
        const out = [];
        for (const li of lis) {
            const h1 = li.querySelector('h1');
            const title = h1 ? h1.textContent.trim() : '';
            const status = li.querySelector('.stateInfo') ? li.querySelector('.stateInfo').textContent.trim() : null;
            const h2 = li.querySelector('h2');
            const h2txt = h2 ? h2.textContent : '';
            const m = h2txt.match(/留言ID:\s*(\d+)/);
            const tid = m ? m[1] : null;
            const timeEl = li.querySelector('.headMainS p');
            const time = timeEl ? timeEl.textContent.replace(/ /g,' ').trim() : null;
            const summary = li.querySelector('.replyContent') ? li.querySelector('.replyContent').textContent.trim() : '';
            const topic = li.querySelector('.domainName') ? li.querySelector('.domainName').textContent.trim() : null;
            const nick = li.querySelector('.nick-name') ? li.querySelector('.nick-name').textContent.trim() : null;
            if (tid) out.push({tid, title, status, time, summary, topic, nick});
        }
        return out;
    }"""
    )
    return items


# ============== 详情页 ==============
def fetch_detail(page, tid):
    url = f"{DETAIL_URL}?tid={tid}"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        log(f"  详情页失败 tid={tid}: {e}")
        return None
    try:
        page.wait_for_function(
            "() => document.querySelector('h1') || document.body.innerText.includes('留言')",
            timeout=20000,
        )
    except Exception:
        pass

    raw = page.evaluate(
        r"""() => {
        const q = s => document.querySelector(s);
        const qa = s => Array.from(document.querySelectorAll(s));
        const title = q('h1') ? q('h1').textContent.trim() : '';
        const typeName = q('.typeNameD') ? q('.typeNameD').textContent.trim() : '';
        const domainName = q('.domainName') ? q('.domainName').textContent.trim() : '';
        const stateInfo = q('.stateInfo') ? q('.stateInfo').textContent.trim() : '';
        const msgContent = q('.replyContentMain') ? q('.replyContentMain').textContent.trim() : '';
        // 官方回复: 可能多条
        const handles = qa('.replyHandleMain').map(el => el.textContent.replace(/ /g,' ').trim());
        const contents = qa('.handleContent').map(el => el.textContent.trim());
        const text = document.body.innerText;
        return {title, typeName, domainName, stateInfo, msgContent, handles, contents, text};
    }"""
    )

    # 解析回复部门/时间/正文
    reply_dept, reply_time, reply_texts = [], [], []
    for i, h in enumerate(raw.get("handles", [])):
        ht = h.replace("官方回复", "").strip()
        mt = re.search(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}", ht)
        t = mt.group(0) if mt else None
        d = re.sub(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}", "", ht).strip(" :") if ht else ""
        reply_dept.append(d)
        reply_time.append(t)
        body = raw.get("contents", [])[i] if i < len(raw.get("contents", [])) else ""
        reply_texts.append(body)

    # 评价状态(可选, 在正文/回复中找标记)
    txt = raw.get("text", "")
    satisfied = None
    if "不满意" in txt:
        satisfied = "不满意"
    elif re.search(r"(网友)?满意", txt):
        satisfied = "满意"

    return {
        "title_detail": raw.get("title"),
        "type_name": raw.get("typeName"),
        "domain_name": raw.get("domainName"),
        "state_detail": raw.get("stateInfo"),
        "msg_content": raw.get("msgContent"),
        "reply_dept": reply_dept,
        "reply_time": reply_time,
        "reply_content": reply_texts,
        "satisfied": satisfied,
        "text_detail": txt,
    }


# ============== 主流程 ==============
def main():
    log("=" * 60)
    log("人民网领导留言板 广州板块爬虫 - 启动")
    log(f"目标时间窗: {DATE_START} ~ {DATE_END}")
    log(f"板块数: {len(FORUMS)} | 每板块最大页数: {MAX_PAGES_PER_FORUM}")
    if ONLY_FORUM:
        log(f"仅跑 fid={ONLY_FORUM}")
    log("=" * 60)

    done_set = load_done()
    log(f"已完成 {len(done_set)} 条, 继续累加")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=UA,
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        page = context.new_page()

        for fid, name, level in FORUMS:
            if ONLY_FORUM and str(fid) != str(ONLY_FORUM):
                continue
            log(f"--- 板块: {name}(fid={fid}, {level}) ---")
            page_num = 1
            empty_pages = 0
            hit_floor = False

            while page_num <= MAX_PAGES_PER_FORUM:
                items = fetch_list_items(page, fid, page_num)
                if not items:
                    empty_pages += 1
                    if empty_pages >= 2:
                        log(f"  连续空页,停止 fid={fid}")
                        break
                    page_num += 1
                    sleep_jitter(SLEEP_LIST)
                    continue
                empty_pages = 0

                keep = []
                earliest_date = None
                for it in items:
                    d = parse_date(it["time"])
                    if d:
                        if earliest_date is None or d < earliest_date:
                            earliest_date = d
                        if DATE_START <= d <= DATE_END:
                            keep.append(it)

                log(
                    f"  p{page_num}: 总 {len(items)} | 窗内 {len(keep)} | "
                    f"最早 {earliest_date}"
                )

                # 列表只返回近两年的留言 -> 到时间窗下限即停
                if earliest_date and earliest_date < DATE_START:
                    log(f"  已到 {DATE_START} 之前(平台列表仅近两年),停止翻页")
                    hit_floor = True

                fetched = 0
                for it in keep:
                    if it["tid"] in done_set:
                        continue
                    detail = fetch_detail(page, it["tid"])
                    if detail:
                        rec = {
                            "tid": it["tid"],
                            "fid": fid,
                            "leader": name,
                            "level": level,
                            "title": detail.get("title_detail") or it["title"],
                            "msg_time": it["time"],
                            "status_list": it["status"],
                            "status_detail": detail.get("state_detail"),
                            "topic_list": it["topic"],
                            "topic_detail": detail.get("domain_name"),
                            "type_name": detail.get("type_name"),
                            "msg_content": detail.get("msg_content"),
                            "reply_dept": detail.get("reply_dept"),
                            "reply_time": detail.get("reply_time"),
                            "reply_content": detail.get("reply_content"),
                            "satisfied": detail.get("satisfied"),
                            "nick": it["nick"],
                            "text_detail": detail.get("text_detail"),
                            "url_detail": f"{DETAIL_URL}?tid={it['tid']}",
                            "fetched_at": datetime.now().isoformat(),
                        }
                        append_jsonl(rec)
                        done_set.add(it["tid"])
                        fetched += 1
                    sleep_jitter(SLEEP_DETAIL)

                log(f"  p{page_num} 详情新增 {fetched} 条, 累计 {len(done_set)}")
                save_done(done_set)

                if hit_floor:
                    break

                page_num += 1
                sleep_jitter(SLEEP_LIST)

        browser.close()

    save_done(done_set)
    log("=" * 60)
    log(f"采集完成, 共 {len(done_set)} 条 -> {DATA_FILE}")
    log("=" * 60)


if __name__ == "__main__":
    main()
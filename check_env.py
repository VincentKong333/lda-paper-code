#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
换机自检脚本 —— 在新电脑上开跑之前, 先执行这个。
================================================================
检查项:
  1) Python 版本(需 >= 3.7)
  2) 第三方依赖(本方案零依赖, 仅用标准库)
  3) config.py 配置是否可读
  4) scraper_collect.py 是否可正常加载
  5) 列表接口连通性 + 签名是否有效(真实请求 1 次)
  6) 详情接口是否可拿到留言正文/回复

用法:
    python3 check_env.py
================================================================
"""
import os, sys, json, platform, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

OK = "  [通过]"
NG = "  [失败]"


def main():
    print("=" * 64)
    print(" 人民网领导留言板爬虫 · 换机环境自检")
    print(f" 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}   系统: {platform.system()} {platform.release()}")
    print("=" * 64)

    # ---------- 1. Python ----------
    print("\n[1] Python 环境")
    v = sys.version_info
    print(f"  解释器: {sys.executable}")
    print(f"  版本:   {sys.version.split()[0]}")
    if v < (3, 7):
        print(NG + " 需要 Python >= 3.7, 请升级后重试")
        return 1
    print(OK + " 版本符合要求 (>= 3.7)")

    # ---------- 2. 依赖 ----------
    print("\n[2] 第三方依赖")
    missing = []
    for mod in ["urllib.request", "json", "hashlib", "csv", "statistics", "subprocess"]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        print(NG + f" 标准库缺失(环境异常): {missing}")
        return 1
    print(OK + " 无需安装任何第三方库 —— 全部使用 Python 标准库")

    # ---------- 3. 配置 ----------
    print("\n[3] 配置检查 (config.py)")
    try:
        import config as CFG
    except Exception as e:
        print(NG + f" 无法导入 config.py: {type(e).__name__}: {e}")
        print("  排查: 确认 config.py 与本脚本在同一目录")
        return 1
    print(OK + " config.py 加载成功")
    print(f"  目标板块: {', '.join(f'{n}({f})' for f, n in CFG.FIDS)}")
    print(f"  输出文件: {CFG.OUT}")
    print(f"  请求节奏: 列表 {CFG.LIST_INTERVAL}s / 详情 {CFG.DETAIL_INTERVAL[0]}~{CFG.DETAIL_INTERVAL[1]}s")
    print(f"  时间窗:   {CFG.WINDOW_START_TS or '不限'} ~ {CFG.WINDOW_END_TS or '今天'}")
    if os.path.dirname(os.path.abspath(CFG.OUT)) != HERE:
        print("  [提示] 输出文件不在本目录, 请确认这是你要的位置")

    # ---------- 4. 采集脚本 ----------
    print("\n[4] 采集脚本加载")
    try:
        import scraper_collect as m
    except Exception as e:
        print(NG + f" 无法导入 scraper_collect.py: {type(e).__name__}: {e}")
        return 1
    print(OK + " scraper_collect.py 可正常导入")

    # ---------- 5. 列表接口 ----------
    print("\n[5] 列表接口连通性 + 签名校验 (真实请求 1 次)")
    fid, fname = CFG.FIDS[0]
    param = {"fid": str(fid), "showUnAnswer": 1, "lastItem": "",
             "position": 0, "rows": 1, "orderType": 2}
    try:
        d = m.call("/v1/threads/list/df", param)
    except Exception as e:
        print(NG + f" 列表接口请求失败: {type(e).__name__}: {e}")
        print("  排查顺序:")
        print("    ① 网络能否正常访问 https://liuyan.people.com.cn")
        print("    ② 若为 HTTP 403: 属于限流, 等几分钟再试即可(不是代码问题)")
        print("    ③ 若返回空数据: 密钥/签名可能已失效, 需重新逆向")
        return 1
    arr = (d.get("resultData") or {}).get("data") or []
    if not arr:
        print(NG + " 接口有响应但无数据 —— 签名或参数被拒")
        print("  返回片段:", json.dumps(d, ensure_ascii=False)[:300])
        return 1
    it = arr[0]
    print(OK + f" 列表接口正常 | {fname}({fid}) 样本 tid={it.get('tid')}"
               f" 标题={str(it.get('subject'))[:20]}")

    # ---------- 6. 详情接口 ----------
    print("\n[6] 详情接口校验 (真实请求 1 次)")
    tid = str(it.get("tid"))
    try:
        det = m.call("/v1/threads/content", {"tid": tid},
                     referer=f"https://liuyan.people.com.cn/threads/content?tid={tid}")
    except Exception as e:
        print(NG + f" 详情接口请求失败: {type(e).__name__}: {e}")
        return 1
    cl = (det.get("resultData") or {}).get("contentList") or []
    if not cl:
        print(NG + " 详情接口未返回 contentList")
        return 1
    has_msg = any(c.get("dataType") == 1 for c in cl)
    has_rep = any(c.get("dataType") == 4 for c in cl)
    print(OK + f" 详情接口正常 | contentList {len(cl)} 段 | "
               f"留言主体={'有' if has_msg else '无'} 官方回复={'有' if has_rep else '无'}")

    # ---------- 汇总 ----------
    print("\n" + "=" * 64)
    print(" 自检全部通过 ✅  可以开始采集")
    print("=" * 64)
    print(" 启动采集:")
    print("   方式A(推荐):  ./start.sh          # 后台启动采集+收尾监控")
    print("   方式B:        nohup python3 scraper_collect.py > collect.log 2>&1 &")
    print("\n 查看进度:")
    print(f"   wc -l {os.path.basename(CFG.OUT)}")
    print("   tail -f collect.log")
    print("\n 停止采集:")
    print("   ./stop.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())

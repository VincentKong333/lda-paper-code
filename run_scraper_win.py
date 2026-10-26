#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Windows 长跑启动器（替代 start.sh）
================================================================
start.sh 依赖 caffeinate / nohup / pgrep，Windows 上都不存在。本脚本等价替代：
  1) 防休眠: ctypes 调 SetThreadExecutionState，阻止系统睡眠(不改动系统电源设置,
     进程退出自动恢复)。这是 caffeinate -i 的 Windows 等价物。
  2) 连通性自检: 开跑前只发 1 次列表请求，签名失效/被墙就立刻退出，不浪费 17 小时。
  3) 全程日志落盘(UTF-8) + PID 文件，便于 stop/monitor。
  4) 断点续跑: 调用 scraper_collect.main()，异常退出不丢进度，重跑即可续。

用法:
  python run_scraper_win.py              # 正常启动
  python run_scraper_win.py --no-awake   # 不阻止休眠
  python run_scraper_win.py --check-only # 只做连通性自检
"""
import ctypes
import datetime
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


def keep_awake(on=True):
    """阻止系统进入睡眠。进程退出后系统恢复正常休眠策略。"""
    if os.name != "nt":
        return False
    try:
        flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0)
        ctypes.windll.kernel32.SetThreadExecutionState(flags)
        return True
    except Exception as e:
        print(f"[警告] 防休眠设置失败: {e}", flush=True)
        return False


def log_path():
    return os.path.join(HERE, f"scraper_run_{time.strftime('%Y%m%d_%H%M%S')}.log")


class Tee:
    """同时写屏幕与日志文件（UTF-8）。"""

    def __init__(self, path):
        self.f = open(path, "a", encoding="utf-8", buffering=1)

    def write(self, s):
        try:
            sys.__stdout__.write(s)
            sys.__stdout__.flush()
        except Exception:
            pass
        self.f.write(s)

    def flush(self):
        try:
            sys.__stdout__.flush()
        except Exception:
            pass
        self.f.flush()


def connectivity_check():
    """只发 1 次列表请求，确认签名仍有效、站点可达。"""
    import config as CFG
    import scraper_collect as SC
    param = {"fid": str(CFG.FIDS[0][0]), "showUnAnswer": 1, "lastItem": "",
             "position": 0, "rows": 1, "orderType": 2}
    d = SC.call_with_retry("/v1/threads/list/df", param, label="precheck")
    arr = d.get("resultData", {}).get("data", [])
    if not arr:
        raise RuntimeError("连通性自检失败: 列表接口返回空")
    it = arr[0]
    print(f"[自检] 通过 | tid={it.get('tid')} | "
          f"{time.strftime('%Y-%m-%d', time.localtime(int(it.get('createDateline') or 0)))} | "
          f"{it.get('subject', '')[:30]}", flush=True)


def main():
    argv = sys.argv[1:]
    no_awake = "--no-awake" in argv
    check_only = "--check-only" in argv

    import config as CFG

    if check_only:
        connectivity_check()
        return

    lp = log_path()
    sys.stdout = sys.stderr = Tee(lp)

    print("=" * 68)
    print("  广州市留言板 · 13 板块全量重采")
    print(f"  启动时间 : {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  输出文件 : {CFG.OUT_NAME}")
    print(f"  时间窗   : {time.strftime('%Y-%m-%d', time.localtime(CFG.WINDOW_START_TS))} ~ "
          f"{time.strftime('%Y-%m-%d', time.localtime(CFG.WINDOW_END_TS))}")
    print(f"  日志     : {os.path.basename(lp)}")
    print("=" * 68)

    if not no_awake:
        ok = keep_awake(True)
        print(f"[防休眠] {'已开启(系统不会睡眠)' if ok else '未开启'}", flush=True)

    pidfile = os.path.join(HERE, "scraper.pid")
    with open(pidfile, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    print(f"[进程] PID={os.getpid()} -> scraper.pid", flush=True)

    t0 = time.time()
    rc = 0
    try:
        connectivity_check()
        import scraper_collect as SC
        SC.main()
    except KeyboardInterrupt:
        print("\n[中断] 收到 Ctrl+C，进度已落盘，重跑本脚本即可续采", flush=True)
        rc = 130
    except Exception:
        print("\n[异常] 进度已落盘，重跑本脚本即可续采", flush=True)
        traceback.print_exc()
        rc = 1
    finally:
        keep_awake(False)
        el = time.time() - t0
        print(f"[结束] 运行 {el / 3600:.2f} 小时, 退出码 {rc}", flush=True)
        try:
            os.remove(pidfile)
        except OSError:
            pass
    sys.exit(rc)


if __name__ == "__main__":
    main()

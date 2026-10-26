#!/bin/bash
# =====================================================================
# 人民网留言板爬虫 · 停止脚本
#   停止采集进程与收尾监控(不会删除任何已采集数据)
#
# 用法:
#   ./stop.sh              # 停止采集 + 监控
#   ./stop.sh --keep-monitor   # 只停采集, 保留监控(让它出报告)
# =====================================================================
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
MYPID=$$

echo "==================== 停止爬虫 ===================="

# ---------- 1. 停采集 ----------
found=0
for p in $(pgrep -f "scraper_collect\.py$" 2>/dev/null); do
    if [ "$p" != "$MYPID" ]; then
        kill "$p" 2>/dev/null && echo "  [已停止] 采集进程 PID $p"
        found=1
    fi
done
[ "$found" = "0" ] && echo "  [跳过] 没有正在运行的采集进程"

# ---------- 2. 停监控 ----------
if [ "${1:-}" = "--keep-monitor" ]; then
    echo "  [保留] 收尾监控继续运行(采集已停, 监控会在文件稳定后自动出报告)"
else
    mfound=0
    for p in $(pgrep -f "monitor_complete\.py$" 2>/dev/null); do
        if [ "$p" != "$MYPID" ]; then
            kill "$p" 2>/dev/null && echo "  [已停止] 监控进程 PID $p"
            mfound=1
        fi
    done
    [ "$mfound" = "0" ] && echo "  [跳过] 没有正在运行的监控进程"
fi

# ---------- 3. 清理 PID 文件 ----------
sleep 2
rm -f scraper.pid monitor.pid 2>/dev/null

# ---------- 4. 确认 ----------
left=$(pgrep -f "scraper_collect\.py$" 2>/dev/null | grep -v "^$MYPID$" | wc -l | tr -d ' ')
OUT_NAME="$(python3 -c 'import config;print(config.OUT_NAME)' 2>/dev/null || echo 'collected_1217_1218.jsonl')"
echo "--------------------------------------------------"
echo "  残留采集进程: $left (0 = 已全部停止)"
if [ -f "$OUT_NAME" ]; then
    echo "  已采集条数  : $(wc -l < "$OUT_NAME" | tr -d ' ')  ($OUT_NAME)"
fi
echo "  数据未删除, 重新 ./start.sh 会自动续跑"
echo "=================================================="

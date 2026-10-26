#!/bin/bash
# =====================================================================
# 人民网留言板爬虫 · 一键后台启动
#   自动识别 python3 → 环境自检 → 后台启动采集 + 收尾监控
#
# 用法:
#   ./start.sh              # 正常启动(先自检)
#   SKIP_CHECK=1 ./start.sh # 跳过自检直接启动
#   ./start.sh --no-monitor # 不启动收尾监控(只采集)
# =====================================================================
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# ---------- 1. 寻找 python3 ----------
PY=""
for c in python3 /usr/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
    if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
    echo "[错误] 未找到 python3, 请先安装 Python 3.7+"
    echo "  macOS:  brew install python3     或去 python.org 下载安装包"
    exit 1
fi
echo "[1/5] 使用解释器: $($PY -c 'import sys;print(sys.executable)')  ($($PY -V 2>&1))"

# ---------- 2. 防重复启动 ----------
if pgrep -f "scraper_collect\.py$" >/dev/null 2>&1; then
    echo "[错误] 已有采集进程在运行, 拒绝重复启动(避免重复写入)。"
    echo "  当前进程:"; pgrep -f "scraper_collect\.py$" | sed 's/^/    PID /'
    echo "  如需重启: 先执行 ./stop.sh"
    exit 1
fi
echo "[2/5] 无正在运行的采集进程, 可以启动"

# ---------- 3. 环境自检(可跳过) ----------
if [ "${SKIP_CHECK:-0}" != "1" ]; then
    echo "[3/5] 环境自检 ..."
    if ! $PY check_env.py; then
        echo "[错误] 自检未通过, 已中止。修好后再启动, 或用 SKIP_CHECK=1 ./start.sh 强制启动。"
        exit 1
    fi
else
    echo "[3/5] 已跳过环境自检 (SKIP_CHECK=1)"
fi

# ---------- 4. 启动采集 ----------
mkdir -p results
OUT_NAME="$($PY -c 'import config;print(config.OUT_NAME)' 2>/dev/null || echo 'collected_1217_1218.jsonl')"
nohup "$PY" scraper_collect.py > collect.log 2>&1 &
SCRAPER_PID=$!
disown 2>/dev/null || true
echo "[4/5] 采集已后台启动  PID=$SCRAPER_PID  日志=collect.log"
echo "$SCRAPER_PID" > scraper.pid

# ---------- 5. 启动收尾监控 ----------
if [ "${1:-}" != "--no-monitor" ]; then
    nohup "$PY" monitor_complete.py > monitor.log 2>&1 &
    MON_PID=$!
    disown 2>/dev/null || true
    echo "[5/5] 收尾监控已启动  PID=$MON_PID  日志=monitor.log"
    echo "$MON_PID" > monitor.pid
    echo "      (采集跑完后会自动出分析报告 + 导出原始数据到 results/)"
else
    echo "[5/5] 未启动收尾监控 (--no-monitor)"
fi

cat <<EOF

==================== 启动完成 ====================
 采集进程 PID : $SCRAPER_PID
 输出文件     : $DIR/$OUT_NAME
 查看进度     : wc -l "$OUT_NAME"
 实时日志     : tail -f collect.log
 停止采集     : ./stop.sh
 收尾产物     : $DIR/results/  (报告 + 原始数据 jsonl/CSV)
==================================================

提示:
 * macOS 合盖/休眠会中断爬虫, 建议执行:  caffeinate -i ./start.sh
 * 这是长时任务(数千条按 4.5~6s/条, 通常数小时), 期间可关闭终端窗口。
 * 中断了也没关系 —— 重新 ./start.sh 会自动跳过已采集的 tid 续跑。
EOF

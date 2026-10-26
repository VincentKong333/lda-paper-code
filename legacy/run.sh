#!/bin/bash
# 后台启动爬虫(全量,断点续跑可重跑)
# 用法:
#   ./run.sh              # 全量,后台跑
#   ./run.sh 1 1217       # 测试,只跑市委书记 1 页
#   ./run.sh 50           # 每板块限 50 页(中规模)

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PY=/Users/vincent/.workbuddy/binaries/python/envs/default/bin/python
LOG="$SCRIPT_DIR/run.out"

cd "$SCRIPT_DIR"

echo "启动: $PY scraper.py $@"
echo "日志: $LOG"
echo "断点: 重跑命令同此,会自动跳过 done.json 中的 tid"

# 后台跑,即使会话退出也继续
nohup "$PY" scraper.py "$@" > "$LOG" 2>&1 &
PID=$!
echo "PID: $PID"

echo "查看进度:"
echo "  tail -f $LOG"
echo "  $PY stats.py"
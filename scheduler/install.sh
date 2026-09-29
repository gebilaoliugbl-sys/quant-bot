#!/bin/bash
# 把下单程序部署到 ~/quant-bot，并注册定时任务：每天 15:00（本机时间）运行 paper_rebalance.py --auto。
#
# 为什么要部署到别处：macOS 不让后台程序读「文稿」文件夹，定时任务只能从文稿以外的地方运行。
# 这个项目文件夹是开发环境（写代码、做实验），~/quant-bot 是生产环境（程序实际跑交易）。
# 密钥 .env、日志 logs/、紧急停止开关 STOP 都放在 ~/quant-bot。
#
# 改了下单相关的代码后，重新运行一次这个脚本就会部署新代码。
#
#   bash scheduler/install.sh           部署、注册，并马上试跑一次
#   bash scheduler/install.sh --print   只打印要注册的定时任务，不做任何改动
#   bash scheduler/uninstall.sh         撤掉定时任务
set -euo pipefail

PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
BOT="$HOME/quant-bot"
LABEL="local.quant.paper-rebalance"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/quant-paper-rebalance.log"
HOUR=15
MINUTE=0

plist() {
cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$BOT/.venv/bin/python</string>
        <string>$BOT/paper_rebalance.py</string>
        <string>--auto</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>$HOUR</integer>
        <key>Minute</key>
        <integer>$MINUTE</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$LOG</string>
    <key>StandardErrorPath</key>
    <string>$LOG</string>
</dict>
</plist>
EOF
}

if [ "${1:-}" = "--print" ]; then
    plist
    exit 0
fi

echo "1. 部署代码到 $BOT"
mkdir -p "$BOT/logs"
rsync -a --delete --exclude __pycache__ "$PROJECT/quant/" "$BOT/quant/"
cp "$PROJECT/paper_rebalance.py" "$BOT/"

echo "2. 准备运行环境（第一次会装 requests，要联网）"
if [ ! -x "$BOT/.venv/bin/python" ]; then
    python3 -m venv "$BOT/.venv"
fi
"$BOT/.venv/bin/pip" install --quiet --upgrade pip requests

echo "3. 密钥和日志"
if [ -f "$PROJECT/.env" ] && [ ! -f "$BOT/.env" ]; then
    mv "$PROJECT/.env" "$BOT/.env"
    echo "   已把 .env 从项目挪到 $BOT/.env"
elif [ -f "$PROJECT/.env" ]; then
    echo "   注意：项目里还有一份 .env，程序只用 $BOT/.env，项目里那份可以删掉"
fi
if [ ! -f "$BOT/.env" ]; then
    echo "   缺少 $BOT/.env：把 .env.example 复制过去，填上模拟账户的密钥，再运行一次这个脚本"
    exit 1
fi
chmod 600 "$BOT/.env"
for f in paper_orders.csv paper_runs.csv; do
    if [ -f "$PROJECT/logs/$f" ] && [ ! -f "$BOT/logs/$f" ]; then
        mv "$PROJECT/logs/$f" "$BOT/logs/$f"
        echo "   已把 logs/$f 挪到 $BOT/logs/"
    fi
done
if [ -f "$PROJECT/STOP" ]; then
    echo "   注意：项目里有一个 STOP 文件，现在紧急停止开关在 $BOT/STOP，项目里那个不再起作用"
fi

echo "4. 注册定时任务：每天 $HOUR:$(printf '%02d' "$MINUTE")"
mkdir -p "$(dirname "$PLIST")" "$(dirname "$LOG")"
plist > "$PLIST"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true   # 之前注册过就先撤掉旧的
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo "5. 马上试跑一次（这个月已经检查过的话，它会直接退出）……"
LINES_BEFORE=$(wc -l < "$LOG" 2>/dev/null || echo 0)   # 只显示这次新增的输出
launchctl kickstart "gui/$(id -u)/$LABEL"
sleep 10
echo "------ 这次运行的输出 ------"
tail -n +"$((LINES_BEFORE + 1))" "$LOG" 2>/dev/null || echo "（还没有输出，过几秒再看：tail $LOG）"
echo "----------------------------"
echo "运行输出都记在 $LOG"

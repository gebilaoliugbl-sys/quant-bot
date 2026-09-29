#!/bin/bash
# 撤掉 install.sh 注册的定时任务。运行记录会保留。
set -euo pipefail

LABEL="local.quant.paper-rebalance"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$PLIST"
echo "已撤掉定时任务 $LABEL"
echo "运行记录保留在 $HOME/Library/Logs/quant-paper-rebalance.log"
echo "$HOME/quant-bot 里的代码、密钥和日志都还在，确定不用了可以整个删掉"

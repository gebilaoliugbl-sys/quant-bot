"""运行时的文件放在哪：密钥、日志、紧急停止开关。

macOS 不让后台程序读「文稿」文件夹，定时任务只能从 ~/quant-bot 运行，
所以这些文件统一放在 ~/quant-bot。不管从哪里运行程序，用的都是同一份。
"""

from pathlib import Path

STATE_DIR = Path.home() / "quant-bot"
ENV_FILE = STATE_DIR / ".env"
LOG_DIR = STATE_DIR / "logs"
STOP_FILE = STATE_DIR / "STOP"

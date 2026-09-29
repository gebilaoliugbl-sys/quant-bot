"""发 macOS 通知：定时任务在后台运行，出了事要让你知道。"""

import subprocess


def notify(title, message):
    """在屏幕右上角弹一条通知。发不出去（比如不在 Mac 上）也不影响程序继续运行。"""
    print(f"[通知] {title}：{message}")
    script = f"display notification {applescript_string(message)} with title {applescript_string(title)}"
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"（通知没发出去：{e}）")


def applescript_string(text):
    """把文字转成 AppleScript 的字符串写法：外面加双引号，里面的反斜杠和双引号要转义。"""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "；") + '"'

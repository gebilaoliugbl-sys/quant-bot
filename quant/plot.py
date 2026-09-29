"""画图的统一样式：固定配色、细线、浅色网格，图上可以直接写中文。"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 只存图片，不弹窗口

import matplotlib.pyplot as plt

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"

# 分类色按固定顺序使用：第 1 条线蓝、第 2 条橙、第 3 条青（已校验色盲也能分清）
COLORS = ["#2a78d6", "#eb6834", "#1baf7a"]

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"


def use_style():
    plt.rcParams.update({
        "font.sans-serif": ["Hiragino Sans GB", "PingFang HK", "Heiti TC", "Arial Unicode MS", "DejaVu Sans"],
        "axes.unicode_minus": False,  # 中文字体常常缺数学减号，改用普通连字符
        "font.size": 10,
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": AXIS,
        "axes.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "axes.labelcolor": INK_SECONDARY,
        "axes.titlecolor": INK,
        "axes.titlesize": 12,
        "xtick.color": AXIS,
        "ytick.color": AXIS,
        "xtick.labelcolor": INK_MUTED,
        "ytick.labelcolor": INK_MUTED,
        "legend.frameon": False,
        "legend.labelcolor": INK_SECONDARY,
        "lines.linewidth": 1.5,
        "lines.solid_capstyle": "round",
        "lines.solid_joinstyle": "round",
    })


def save_figure(fig, name):
    """把图存到项目的 output/ 目录，并打印路径。"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / name
    fig.savefig(path, dpi=150, bbox_inches="tight")
    print(f"图已保存到 {path}")


def label_line_end(ax, series, text, color):
    """在线的末端画一个点，旁边写上文字。文字用墨色，颜色只留给点。"""
    x, y = series.index[-1], series.iloc[-1]
    ax.plot(x, y, "o", ms=6, color=color, mec=SURFACE, mew=1.5, zorder=3)
    ax.annotate(text, (x, y), xytext=(7, 0), textcoords="offset points",
                va="center", color=INK_SECONDARY, fontsize=9, annotation_clip=False)

"""研究：试了很多次之后，t 值要多高才能信？（多重检验）

t 值大于 2 的老规矩，只在"只试了一次"时成立。试的次数一多，光靠运气就能撞出很高的 t 值。

一、模拟：每个"世界"里有 N 个毫无本事的策略（每月收益纯随机、平均为 0），各跑 20 年，
    记下其中最高的 |t|。重复 500 个世界，看"光靠运气能达到的 |t|"怎么随 N 上升。
    反着做也是一个策略，所以看绝对值。
二、门槛：试了 N 次，要把"至少有一个是假发现"的概率控制在 5% 以内，
    |t| 至少要多高（Bonferroni 修正：把 5% 的犯错额度平分给 N 次尝试）。

运行（在项目根目录）：.venv/bin/python -m research.multiple_testing
"""

from statistics import NormalDist

import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter

from quant.plot import COLORS, INK_MUTED, INK_SECONDARY, plt, save_figure, use_style

N_TRIED = [1, 3, 10, 30, 100, 300, 1000]
WORLDS = 500
MONTHS = 240  # 20 年


def main():
    rng = np.random.default_rng(0)
    best = {n: [] for n in N_TRIED}
    for _ in range(WORLDS):
        returns = rng.normal(0, 0.04, size=(MONTHS, max(N_TRIED)))  # 每月平均 0、波动 4%，毫无本事
        t = returns.mean(axis=0) / (returns.std(axis=0, ddof=1) / np.sqrt(MONTHS))
        for n in N_TRIED:
            best[n].append(np.abs(t[:n]).max())  # 前 n 个策略里最好的那个

    table = pd.DataFrame({
        n: {
            "运气能到的最高 |t|（中位数）": np.median(best[n]),
            "运气能到的最高 |t|（95% 的世界不超过）": np.quantile(best[n], 0.95),
            "至少撞出一个 |t|>2 的世界": np.mean(np.array(best[n]) > 2),
            "门槛（Bonferroni）": NormalDist().inv_cdf(1 - 0.025 / n),
        }
        for n in N_TRIED
    }).T
    table.index.name = "试了几个策略"
    pd.set_option("display.unicode.east_asian_width", True)
    print(f"每个策略跑 {MONTHS // 12} 年，模拟 {WORLDS} 个世界\n")
    print(table.to_string(formatters={
        "运气能到的最高 |t|（中位数）": "{:.2f}".format,
        "运气能到的最高 |t|（95% 的世界不超过）": "{:.2f}".format,
        "至少撞出一个 |t|>2 的世界": "{:.0%}".format,
        "门槛（Bonferroni）": "{:.2f}".format,
    }))
    plot(table)


def plot(table):
    use_style()
    fig, ax = plt.subplots(figsize=(9, 5.5))
    n = table.index.to_numpy()
    median = table["运气能到的最高 |t|（中位数）"]
    top = table["运气能到的最高 |t|（95% 的世界不超过）"]
    ax.fill_between(n, median, top, color=COLORS[1], alpha=0.12, linewidth=0)
    ax.plot(n, median, color=COLORS[0], marker="o", ms=5, label="运气能到的最高 |t|：中位数")
    ax.plot(n, top, color=COLORS[1], marker="o", ms=5, label="运气能到的最高 |t|：95% 的世界不超过")
    # 两条参考线的说明放在图上空着的地方：t=2 在右边线上方，t=3 在左边线下方
    for level, text, x, dy, ha in [(2, "t = 2：只试一次时的老规矩", n[-1], 4, "right"),
                                   (3, "t = 3：学术界对新因子的建议门槛", n[0], -14, "left")]:
        ax.axhline(level, color=INK_MUTED, linewidth=1, linestyle="--")
        ax.annotate(text, (x, level), xytext=(0, dy), textcoords="offset points", ha=ha,
                    color=INK_SECONDARY, fontsize=9)
    ax.set_xscale("log")
    ax.set_xticks(n)
    ax.set_xticks([], minor=True)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:g}"))
    ax.set_xlabel("试了几个毫无本事的策略")
    ax.set_ylabel("其中最好的那个的 |t|")
    ax.set_title("试得越多，光靠运气就能撞出越高的 t 值", loc="left")
    ax.legend(loc="upper left", bbox_to_anchor=(0, 0.93))
    print()
    save_figure(fig, "research_multiple_testing.png")


if __name__ == "__main__":
    main()

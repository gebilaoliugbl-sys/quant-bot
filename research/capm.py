"""研究：拆开收益——策略赚的钱里，多少只是"跟着大盘"，多少是它自己的？（CAPM 回归）

用每个月的超额收益（减掉国债利息）做回归：
  策略的超额收益 = alpha + beta × 大盘（SPY）的超额收益 + 误差
  beta：跟着大盘动的程度。1 表示大盘涨 1% 它也涨 1%
  alpha：扣掉跟着大盘的部分之后，每年多出来的收益
  t 值：alpha 的 t 值绝对值大于 2，大致有 95% 的把握它不是 0，不是运气
  R²：策略每个月的涨跌，有多少能被大盘的涨跌解释

拿前面研究过的几个策略来拆。第一行是 SPY 对它自己回归，用来检验工具：应该正好 beta 1、alpha 0。

运行（在项目根目录）：.venv/bin/python -m research.capm
"""

import numpy as np
import pandas as pd
from matplotlib.ticker import PercentFormatter

from quant.data import load_prices
from quant.metrics import TRADING_DAYS
from quant.plot import COLORS, INK_SECONDARY, plt, save_figure, use_style
from quant.stats import regress
from research import survivorship, trend_filter


def monthly(daily):
    """日收益换成月收益：一个月里每天的 (1 + 收益) 连乘，再减 1。"""
    return (1 + daily).groupby(daily.index.to_period("M")).prod() - 1


def main():
    close = load_prices("SPY")["Close"]
    market = close.pct_change()
    rate = load_prices("^IRX")["Close"].reindex(close.index).ffill() / 100 / TRADING_DAYS

    bot_runs, *_ = trend_filter.build()
    top_runs, *_ = survivorship.build()
    strategies = {
        "SPY 自己（检验工具）": market.loc[bot_runs["A 各 1/3 一直拿着"].index],
        "A 机器人现在的策略": bot_runs["A 各 1/3 一直拿着"],
        "B 加趋势过滤": bot_runs["B 加趋势过滤"],
        "事后挑的前 10 大": top_runs["今天的前 10 大（事后挑的）"],
    }

    rows, points = {}, {}
    for name, r in strategies.items():
        days = r.index  # 大盘和国债利息都只取策略有数据的那些天，月份才对得齐
        y = monthly(r) - monthly(rate.loc[days])
        x = (monthly(market.loc[days]) - monthly(rate.loc[days])).rename("beta")
        res = regress(y, x.to_frame())
        rows[name] = {
            "期间": f"{days[0]:%Y-%m} 至 {days[-1]:%Y-%m}",
            "beta": res["coef"]["beta"],
            "年化 alpha": res["coef"]["alpha"] * 12,
            "alpha 的 t 值": res["t"]["alpha"],
            "R²": res["r2"],
        }
        points[name] = (x, y, res)

    pd.set_option("display.unicode.east_asian_width", True)
    table = pd.DataFrame(rows).T
    print(table.to_string(na_rep="—", formatters={
        "beta": "{:.2f}".format, "年化 alpha": "{:+.1%}".format,
        "alpha 的 t 值": "{:.1f}".format, "R²": "{:.2f}".format,
    }))
    plot({k: points[k] for k in ("A 机器人现在的策略", "事后挑的前 10 大")})


def plot(points):
    use_style()
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.axhline(0, color=INK_SECONDARY, linewidth=0.6)
    ax.axvline(0, color=INK_SECONDARY, linewidth=0.6)
    for (name, (x, y, res)), color in zip(points.items(), COLORS):
        label = f"{name}：beta {res['coef']['beta']:.2f}，年化 alpha {res['coef']['alpha'] * 12:+.1%}"
        ax.scatter(x, y, s=14, color=color, alpha=0.55, linewidths=0, label=label)
        line_x = np.linspace(x.min(), x.max(), 2)
        ax.plot(line_x, res["coef"]["alpha"] + res["coef"]["beta"] * line_x, color=color, linewidth=2)
    ax.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.set_xlabel("大盘（SPY）当月的超额收益")
    ax.set_ylabel("策略当月的超额收益")
    ax.set_title("每个点是一个月：斜率是 beta，直线在 0 处的高度是 alpha", loc="left")
    ax.legend(loc="upper left")
    print()
    save_figure(fig, "research_capm.png")


if __name__ == "__main__":
    main()

"""研究：用"今天最大的 10 家公司"回测过去，会得到什么？——演示幸存者偏差

做法：2013 年初等额买入今天（2026-09-29）市值最大的 10 家美国公司，每月调回等额，
和同期一直持有 SPY 比。这 10 家正是因为过去涨得最好，才成了今天最大的，
所以这个回测等于先知道了答案再去"预测"，结果一定好得离谱。它不是一个能用的策略。

公平的比较对象是 SPY：它每个时期持有的都是当时的标普 500 成分股，包括后来衰落、被剔除的公司。

运行（在项目根目录）：.venv/bin/python -m research.survivorship
"""

import pandas as pd
from matplotlib.ticker import FuncFormatter

from quant.data import load_prices
from quant.metrics import TRADING_DAYS, annual_volatility, cagr, equity_curve, max_drawdown, sharpe_ratio
from quant.plot import COLORS, label_line_end, plt, save_figure, use_style
from quant.portfolio import monthly_portfolio

# 2026-09-29 查到的市值前 10 名（英伟达、苹果、谷歌、微软、亚马逊、Meta、博通、特斯拉、伯克希尔、礼来）
TOP_TODAY = ["NVDA", "AAPL", "GOOGL", "MSFT", "AMZN", "META", "AVGO", "TSLA", "BRK-B", "LLY"]
START = "2013-01-01"  # 这 10 家那时都已经上市（Meta 最晚，2012 年 5 月）
COST_BPS = 5


def main():
    runs, rate, returns = build()

    pd.set_option("display.unicode.east_asian_width", True)
    table = pd.DataFrame({
        name: {"年化收益": cagr(r), "年化波动": annual_volatility(r),
               "夏普": sharpe_ratio(r - rate.loc[r.index]), "最大回撤": max_drawdown(r),
               "1 美元变成": equity_curve(r).iloc[-1]}
        for name, r in runs.items()
    }).T
    print(f"{returns.index[0]:%Y-%m} 至 {returns.index[-1]:%Y-%m}\n")
    print(table.to_string(formatters={"年化收益": "{:.1%}".format, "年化波动": "{:.1%}".format,
                                      "夏普": "{:.2f}".format, "最大回撤": "{:.0%}".format,
                                      "1 美元变成": "{:.1f}".format}))

    each = pd.Series({t: cagr(returns[t]) for t in TOP_TODAY}).sort_values(ascending=False)
    spy = cagr(returns["SPY"])
    print(f"\n每一家的年化收益（SPY 是 {spy:.1%}）：")
    print("  " + "，".join(f"{t} {v:.0%}" for t, v in each.items()))
    print(f"10 家里有 {(each > spy).sum()} 家跑赢了 SPY")
    plot(runs)


def build():
    """返回 (runs, rate, returns)：两种做法的日收益、每天的国债利息、各股票和 SPY 的日收益。"""
    close = pd.DataFrame({t: load_prices(t)["Close"] for t in TOP_TODAY + ["SPY"]}).loc[START:].dropna()
    rate = load_prices("^IRX")["Close"].reindex(close.index).ffill() / 100 / TRADING_DAYS
    returns = close.pct_change().iloc[1:]

    month_starts = returns.index.to_series().groupby(returns.index.to_period("M")).first()
    equal = pd.DataFrame(1 / len(TOP_TODAY), index=month_starts.values, columns=TOP_TODAY)
    runs = {
        "今天的前 10 大（事后挑的）": monthly_portfolio(returns[TOP_TODAY], equal, COST_BPS),
        "SPY（当时就能买到的）": returns["SPY"],
    }
    return runs, rate, returns


def plot(runs):
    use_style()
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for (name, r), color in zip(runs.items(), COLORS):
        equity = equity_curve(r)
        ax.plot(equity, color=color, label=name)
        label_line_end(ax, equity, f"{equity.iloc[-1]:.0f} 美元", color)
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:g}"))
    ax.yaxis.set_minor_formatter(FuncFormatter(lambda y, _: ""))
    ax.set_ylabel("1 美元变成多少（对数刻度）")
    ax.set_title("幸存者偏差：用今天的赢家回测过去，结果好得不真实", loc="left")
    ax.legend(loc="upper left")
    print()
    save_figure(fig, "research_survivorship.png")


if __name__ == "__main__":
    main()

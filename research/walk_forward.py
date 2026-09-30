"""研究：滚动的样本外检验（walk-forward）——挑参数时不偷看答案，结果会差多少？

策略：SPY 的均线择时，均线天数从 20 到 300 里挑（和第 2 课一样，共 29 个）。

滚动选择：每年年初，只用那一年之前的全部数据，挑出夏普最高的天数，用它交易接下来的一年。
         把每一年的结果接起来，就是一个"边走边学"的人真正能拿到的收益。
对照：
  事后选的最佳天数：用 2000 年以后全部结果挑出最好的（偷看了答案）
  固定 200 天：一开始就定好，不挑
  一直持有 SPY

另外比较：挑参数时只看过去 5 年、2 年、1 年，而不是全部历史，结果怎样、参数换得多频繁。

夏普按第 2 课的简化算法（不减国债利息），空仓时现金也不算利息。

运行（在项目根目录）：.venv/bin/python -m research.walk_forward
"""

import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter

from quant.backtest import run_backtest
from quant.data import load_prices
from quant.metrics import annual_volatility, cagr, equity_curve, max_drawdown, sharpe_ratio
from quant.plot import COLORS, INK_MUTED, plt, save_figure, use_style

WINDOWS = range(20, 310, 10)
COST_BPS = 5
FIRST_YEAR = 2000  # 第一个交易年；在它之前的数据只用来挑参数


def main():
    close = load_prices("SPY")["Close"]
    asset = close.pct_change().fillna(0.0)
    start = close.index[max(WINDOWS)]  # 最长的均线也有值之后，才开始评估
    results = {w: run_backtest(close, (close > close.rolling(w).mean()).astype(float), COST_BPS) for w in WINDOWS}
    returns = pd.DataFrame({w: r["strategy"] for w, r in results.items()}).loc[start:]
    positions = pd.DataFrame({w: r["position"] for w, r in results.items()}).loc[start:]

    years = range(FIRST_YEAR, close.index[-1].year + 1)
    walk, chosen = walk_forward(returns, positions, asset, years)

    oos = returns.loc[f"{FIRST_YEAR}-01-01":]
    best = oos.apply(sharpe_ratio).idxmax()
    runs = {
        f"事后选的最佳天数（{best} 天，偷看了答案）": oos[best],
        "滚动选择（每年只用过去的数据挑）": walk,
        "固定 200 天": oos[200],
        "一直持有 SPY": asset.loc[oos.index],
    }

    pd.set_option("display.unicode.east_asian_width", True)
    table = pd.DataFrame({
        name: {"年化收益": cagr(r), "年化波动": annual_volatility(r), "夏普": sharpe_ratio(r), "最大回撤": max_drawdown(r)}
        for name, r in runs.items()
    }).T
    print(f"{oos.index[0]:%Y-%m} 至 {oos.index[-1]:%Y-%m}，每次买卖成本 {COST_BPS / 100:g}%\n")
    print(table.to_string(formatters={"年化收益": "{:.1%}".format, "年化波动": "{:.1%}".format,
                                      "夏普": "{:.2f}".format, "最大回撤": "{:.0%}".format}))
    print("\n滚动选择每年挑中的天数：")
    print("  " + "，".join(f"{y}: {w}" for y, w in chosen.items()))

    rows = {}
    for lookback in (None, 5, 2, 1):
        r, picks = walk_forward(returns, positions, asset, years, lookback)
        label = "全部历史" if lookback is None else f"过去 {lookback} 年"
        rows[f"挑参数时看{label}"] = {
            "年化收益": cagr(r), "夏普": sharpe_ratio(r), "最大回撤": max_drawdown(r),
            "换参数次数": sum(picks[y] != picks[y - 1] for y in list(years)[1:]),
            "挑过几种天数": len(set(picks.values())),
        }
    print(f"\n挑参数时往回看多久？（{len(years)} 年里）\n")
    print(pd.DataFrame(rows).T.to_string(formatters={
        "年化收益": "{:.1%}".format, "夏普": "{:.2f}".format, "最大回撤": "{:.0%}".format,
        "换参数次数": "{:.0f}".format, "挑过几种天数": "{:.0f}".format}))
    plot(runs)


def walk_forward(returns, positions, asset, years, lookback=None):
    """每年年初用过去的数据挑夏普最高的均线天数，交易这一年。返回 (日收益, {年份: 选中的天数})。

    lookback 是往回看几年，None 表示用之前的全部历史。
    """
    chosen = {}
    for y in years:
        past = returns.loc[: f"{y - 1}-12-31"] if lookback is None else returns.loc[f"{y - lookback}-01-01": f"{y - 1}-12-31"]
        # 几个天数整段都满仓时，收益一模一样、并列第一，idxmax 取最小的那个。
        # 只在往回看 1、2 年时出现；换成取最大的，那两行的数字会变一点，结论不变
        with np.errstate(invalid="ignore", divide="ignore"):  # 整段都空仓的天数，收益全是 0，夏普算不出来，跳过
            chosen[y] = past.apply(sharpe_ratio).idxmax()
    # 把每一年选中的那个天数的仓位接起来，再统一算收益和成本（换天数那天的买卖也要付成本）
    position = pd.concat([positions.loc[str(y), chosen[y]] for y in years])
    turnover = position.diff().abs().fillna(position.iloc[0])
    return position * asset.loc[position.index] - turnover * COST_BPS / 10_000, chosen


def plot(runs):
    use_style()
    fig, ax = plt.subplots(figsize=(10, 6))
    styles = [dict(color=COLORS[1]), dict(color=COLORS[0], linewidth=2.2), dict(color=COLORS[2]),
              dict(color=INK_MUTED, linestyle="--")]
    for (name, r), style in zip(runs.items(), styles):
        equity = equity_curve(r)
        # 有两条线最后几乎停在同一个数，线尾标签会叠在一起，所以最终金额写进图例
        ax.plot(equity, label=f"{name}：{equity.iloc[-1]:.1f} 美元", **{"linewidth": 1.5, **style})
    ax.set_yscale("log")
    ax.set_yticks([0.5, 1, 2, 4, 8])
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:g}"))
    ax.yaxis.set_minor_formatter(FuncFormatter(lambda y, _: ""))
    ax.set_ylabel("1 美元变成多少（对数刻度）")
    ax.set_title("SPY 均线择时：挑参数时偷看答案 vs 边走边学", loc="left")
    ax.legend(loc="upper left")
    print()
    save_figure(fig, "research_walk_forward.png")


if __name__ == "__main__":
    main()

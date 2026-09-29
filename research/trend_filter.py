"""研究：股票、国债、黄金各 1/3 的组合，加上趋势过滤会不会更好？

A（现在的机器人）：SPY、IEF、GLD 各 1/3，每月第一个交易日调回比例。
B（候选）：每月底看一眼，哪样的收盘价在 200 日均线之下，下个月就不拿它，
           那 1/3 换成现金，拿 13 周美国国债的利息。

看结果之前定好的标准：
  以 2016-01-01 为界分成前后两段。B 要在两段里都比 A 夏普更高、最大回撤更小
  （都算上交易成本），才考虑把机器人换成 B。均线天数固定 200，不调参数。

夏普按正式定义算：用超出国债利息的那部分收益。

运行（在项目根目录）：.venv/bin/python -m research.trend_filter
"""

import pandas as pd
from matplotlib.ticker import FuncFormatter, PercentFormatter

from quant.data import load_prices
from quant.metrics import TRADING_DAYS, annual_volatility, cagr, drawdown, equity_curve, max_drawdown, sharpe_ratio
from quant.plot import COLORS, label_line_end, plt, save_figure, use_style
from quant.portfolio import monthly_portfolio

ASSETS = ["SPY", "IEF", "GLD"]
WINDOW = 200
COST_BPS = 5
SPLIT = "2016-01-01"


def main():
    close = pd.DataFrame({t: load_prices(t)["Close"] for t in ASSETS}).dropna()
    rate = load_prices("^IRX")["Close"].reindex(close.index).ffill() / 100 / TRADING_DAYS  # 国债年利率换成每天的利息
    returns = close.pct_change().assign(CASH=rate)

    # 每个月的判断只用上个月最后一个交易日的数据：那天收盘价在 200 日均线之上吗
    months = close.index.to_period("M")
    sma = close.rolling(WINDOW).mean()
    above = (close > sma).groupby(months).last().shift(1)
    ready = sma.notna().all(axis=1).groupby(months).last().shift(1, fill_value=False)
    month_starts = close.index.to_series().groupby(months).first()

    hold_all = pd.DataFrame(1 / 3, index=above.index, columns=ASSETS).assign(CASH=0.0)
    trend = above[ASSETS].astype(float) / 3
    trend["CASH"] = 1 - trend.sum(axis=1)
    targets = {"A 各 1/3 一直拿着": hold_all, "B 加趋势过滤": trend}

    start = month_starts[ready.astype(bool)].iloc[0]  # 上个月底均线已经有值的第一个月
    returns = returns.loc[start:]
    runs = {}
    for name, t in targets.items():
        t = t[ready.astype(bool)].set_index(month_starts[ready.astype(bool)])
        runs[name] = monthly_portfolio(returns, t, COST_BPS)

    report(runs, rate.loc[start:], trend[ready.astype(bool)])
    plot(runs)


def stats(r, rate):
    return {"年化收益": cagr(r), "年化波动": annual_volatility(r),
            "夏普": sharpe_ratio(r - rate.loc[r.index]), "最大回撤": max_drawdown(r)}


def report(runs, rate, trend):
    pd.set_option("display.unicode.east_asian_width", True)
    fmt = {"年化收益": "{:.1%}".format, "年化波动": "{:.1%}".format, "夏普": "{:.2f}".format, "最大回撤": "{:.0%}".format}
    first = next(iter(runs.values()))
    periods = {
        f"全部（{first.index[0]:%Y-%m} 至 {first.index[-1]:%Y-%m}）": slice(None, None),
        "前一段（2016 年以前）": slice(None, "2015-12-31"),
        "后一段（2016 年以后）": slice(SPLIT, None),
    }
    tables = {}
    for label, period in periods.items():
        tables[label] = pd.DataFrame({name: stats(r.loc[period], rate) for name, r in runs.items()}).T
        print(f"\n{label}\n")
        print(tables[label].to_string(formatters=fmt))

    print("\n几个特别的年份：")
    for year in ("2008", "2020", "2022"):
        line = "，".join(f"{name[0]} {(1 + r.loc[year]).prod() - 1:+.1%}" for name, r in runs.items())
        print(f"  {year} 年：{line}")

    switches = (trend.diff().abs().sum(axis=1) > 0).sum() / (len(trend) / 12)
    print(f"\nB 平均有 {trend['CASH'].mean():.0%} 的钱放在现金里，每年调整持仓 {switches:.1f} 次")

    a, b = list(runs)
    halves = [tables[label] for label in list(periods)[1:]]
    passed = all(t.loc[b, "夏普"] > t.loc[a, "夏普"] and t.loc[b, "最大回撤"] > t.loc[a, "最大回撤"] for t in halves)
    print(f"\n按事先定好的标准（两段里都夏普更高、最大回撤更小）：{'B 通过，可以考虑换' if passed else 'B 没通过，机器人保持现在的策略'}")


def plot(runs):
    use_style()
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(10, 7), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    for (name, r), color in zip(runs.items(), COLORS):
        equity = equity_curve(r)
        top.plot(equity, color=color, label=name)
        label_line_end(top, equity, f"{equity.iloc[-1]:.1f} 美元", color)
        bottom.plot(drawdown(r), color=color, label=name)
    top.set_yscale("log")
    top.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:g}"))
    top.yaxis.set_minor_formatter(FuncFormatter(lambda y, _: f"{y:g}"))  # 范围不到 10 倍时，刻度都是次刻度
    top.set_ylabel("1 美元变成多少（对数刻度）")
    top.set_title("股票、国债、黄金各 1/3：加不加趋势过滤", loc="left")
    top.legend(loc="upper left")
    bottom.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    bottom.set_ylabel("回撤（离前高跌了多少）")
    bottom.legend(loc="lower right")
    print()
    save_figure(fig, "research_trend_filter.png")


if __name__ == "__main__":
    main()

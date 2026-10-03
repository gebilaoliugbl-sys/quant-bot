"""研究：风险平价——按波动的倒数分钱，每份风险换来的收益会不会比各 1/3 多？

计划、文献和判断标准在 research/risk_parity_plan.md，是看结果之前写好并提交的（git 提交 b6879eb）。
数据是 1975 年以来股票、国债、黄金、国库券的月收益（quant/history.py），前 36 个月只用来估计波动。

一、主检验：风险平价对比各 1/3，再对比"各 1/3 掺国库券、把波动降到一样"，按计划里的三条标准判断。
二、参考：几个别的版本，只看，不参与决定。

计划里没写明、写代码时定的细节：
  - 每个月的比例只用到上个月为止的数据；调仓前的比例，是上个月的比例按各资产当月的涨跌漂移以后的
  - 评估的第一个月（1978-01）当作已经按目标比例持有，不算建仓成本
  - 波动用月收益的标准差（ddof=1）；掺国库券的对照，预计波动用同样 36 个月的协方差
  - 自助法：12 个月一块，块的起点均匀随机，拼够月数再截掉多余的，随机种子 0

运行（在项目根目录）：.venv/bin/python -m research.risk_parity
"""

import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter

from quant.data import load_prices
from quant.history import load_history
from quant.metrics import max_drawdown
from quant.plot import COLORS, INK_MUTED, INK_SECONDARY, plt, save_figure, use_style

ASSETS = ["stocks", "bonds", "gold"]
NAMES = {"stocks": "股票", "bonds": "国债", "gold": "黄金"}
ETFS = {"stocks": "SPY", "bonds": "IEF", "gold": "GLD"}
FEES = {"stocks": 0.0009, "bonds": 0.0015, "gold": 0.0040}   # ETF 每年的管理费
WINDOW = 36
COST = 0.0005
EVAL = ("1978-01", "2026-08")
RISING = [("1978-01", "1981-09"), ("2020-08", "2026-08")]     # 10 年期国债利率上升的年代
FALLING = [("1981-10", "2020-07")]                             # 利率下降的年代
BOOTSTRAPS = 10_000
BLOCK = 12


def main():
    history = load_history()
    returns, rf = history[ASSETS], history["rf"]
    pd.set_option("display.unicode.east_asian_width", True)

    equal = equal_weights(returns)
    parity = inverse_vol_weights(returns)
    matched = risk_matched(returns, parity)
    assert str(parity.dropna().index[0]) == EVAL[0]  # 前 36 个月只用来估计波动
    runs = {"各 1/3": equal, "风险平价": parity, "各 1/3 掺国库券": matched}
    results = {name: portfolio(w, returns, rf) for name, w in runs.items()}

    primary_test(runs, results, rf)
    references(returns, rf, equal, parity, matched, results)
    plot(results, parity, rf)


def equal_weights(returns):
    return pd.DataFrame(1 / 3, index=returns.index, columns=returns.columns)


def inverse_vol_weights(returns, window=WINDOW):
    """每个月按过去 window 个月的波动倒数分钱，只用到上个月为止的数据。"""
    inverse = 1 / returns.rolling(window).std().shift(1)
    return inverse.div(inverse.sum(axis=1), axis=0)


def erc_weights(returns, window=WINDOW):
    """等风险贡献：考虑相关性，让每样资产对组合波动的贡献一样大。"""
    rows = {returns.index[i]: solve_erc(returns.iloc[i - window:i].cov().to_numpy())
            for i in range(window, len(returns))}
    return pd.DataFrame.from_dict(rows, orient="index", columns=returns.columns).reindex(returns.index)


def solve_erc(cov, tol=1e-12):
    """循环坐标下降（Griveau-Billion、Richard、Roncalli 2013），收敛后每样资产的风险贡献相等。"""
    n = len(cov)
    y = 1 / np.sqrt(np.diag(cov))
    for _ in range(1000):
        previous = y.copy()
        for i in range(n):
            rest = (cov[i] * y).sum() - cov[i, i] * y[i]
            y[i] = (-rest + np.sqrt(rest ** 2 + 4 * cov[i, i] / n)) / (2 * cov[i, i])
        if np.abs(y - previous).max() < tol:
            break
    return y / y.sum()


def risk_matched(returns, parity, window=WINDOW):
    """各 1/3 掺国库券：每个月把预计波动降到和风险平价一样，最多 100% 投资。"""
    equal = np.full(len(returns.columns), 1 / 3)
    scale = {}
    for i in range(window, len(returns)):
        cov = returns.iloc[i - window:i].cov().to_numpy()
        w = parity.iloc[i].to_numpy()
        scale[returns.index[i]] = min(1.0, np.sqrt((w * (cov @ w)).sum()) / np.sqrt((equal * (cov @ equal)).sum()))
    return equal_weights(returns).mul(pd.Series(scale).reindex(returns.index), axis=0)


def portfolio(weights, returns, rf, cost=COST, start=EVAL[0], fees=None):
    """每月月初调到目标比例，剩下的钱放国库券。返回 (每月扣成本后的总收益, 每月换手量)。

    换手量 = 各资产的目标比例和调仓前比例之差的绝对值之和；调仓前比例是上个月的比例按当月涨跌漂移以后的。
    fees：每年的管理费，按持有比例每月扣掉十二分之一。
    """
    weights = weights.loc[start:]
    returns, rf = returns.loc[weights.index], rf.loc[weights.index]
    gross = (weights * returns).sum(axis=1) + (1 - weights.sum(axis=1)) * rf
    drifted = (weights * (1 + returns)).div(1 + gross, axis=0)
    turnover = (weights - drifted.shift(1)).abs().sum(axis=1)
    turnover.iloc[0] = 0.0  # 第一个月当作已经按目标比例持有
    net = gross - cost * turnover
    if fees:
        net -= (weights * pd.Series(fees) / 12).sum(axis=1)
    return net, turnover


def sharpe(excess):
    """夏普：月超额收益的均值 ÷ 标准差 × √12。"""
    return excess.mean() / excess.std() * np.sqrt(12)


def annual(net):
    return (1 + net).prod() ** (12 / len(net)) - 1


def summary(net, turnover, weights, rf):
    w = weights.loc[net.index]
    return {
        "年化收益": annual(net), "年化波动": net.std() * np.sqrt(12),
        "夏普": sharpe(net - rf.loc[net.index]), "最大回撤": max_drawdown(net),
        **{NAMES[a]: w[a].mean() for a in ASSETS}, "国库券": 1 - w.sum(axis=1).mean(),
        "每年换手": turnover.mean() * 12,
    }


def bootstrap_share(a, b, n=BOOTSTRAPS, block=BLOCK, seed=0):
    """两列月超额收益配对地按 block 个月一块随机重拼 n 次，返回 b 的夏普高于 a 的比例。"""
    rng = np.random.default_rng(seed)
    a, b = a.to_numpy(), b.to_numpy()
    length = len(a)
    starts = rng.integers(0, length - block + 1, size=(n, -(-length // block)))
    index = (starts[:, :, None] + np.arange(block)).reshape(n, -1)[:, :length]
    ratio = lambda x: x[index].mean(axis=1) / x[index].std(axis=1, ddof=1)  # noqa: E731（√12 两边一样，省掉）
    return float((ratio(b) > ratio(a)).mean())


def regime_sharpe(net, rf, periods):
    excess = pd.concat([(net - rf.loc[net.index]).loc[a:b] for a, b in periods])
    return sharpe(excess)


TABLE_FORMAT = {"年化收益": "{:.1%}".format, "年化波动": "{:.1%}".format, "夏普": "{:.2f}".format,
                "最大回撤": "{:.0%}".format, "股票": "{:.0%}".format, "国债": "{:.0%}".format,
                "黄金": "{:.0%}".format, "国库券": "{:.0%}".format, "每年换手": "{:.0%}".format}


def primary_test(runs, results, rf):
    table = pd.DataFrame({name: summary(*results[name], runs[name], rf) for name in runs}).T
    print(f"一、主检验（{EVAL[0]} 至 {EVAL[1]}，过去 {WINDOW} 个月的波动定比例，调仓成本 {COST:.2%}；"
          f"比例是平均值）\n")
    print(table.to_string(formatters=TABLE_FORMAT))

    (eq, _), (rp, _), (mt, _) = results["各 1/3"], results["风险平价"], results["各 1/3 掺国库券"]
    share = bootstrap_share(eq - rf.loc[eq.index], rp - rf.loc[rp.index])
    print(f"\n自助法：按 {BLOCK} 个月一块随机重拼 {BOOTSTRAPS:,} 次，风险平价夏普更高的比例 {share:.1%}")

    regimes = {"利率下降的年代（1981-10 至 2020-07）": FALLING, "利率上升的年代（两段合起来）": RISING,
               "  其中 1978-01 至 1981-09": RISING[:1], "  其中 2020-08 至 2026-08": RISING[1:]}
    print("\n分年代的夏普（各 1/3 对 风险平价）：")
    split = {}
    for label, periods in regimes.items():
        split[label] = (regime_sharpe(eq, rf, periods), regime_sharpe(rp, rf, periods))
        print(f"  {label}：{split[label][0]:.3f} 对 {split[label][1]:.3f}")

    rp_row, eq_row, mt_row = table.loc["风险平价"], table.loc["各 1/3"], table.loc["各 1/3 掺国库券"]
    falling, rising = split["利率下降的年代（1981-10 至 2020-07）"], split["利率上升的年代（两段合起来）"]
    checks = [
        (f"1. 整个评估期夏普更高（{rp_row['夏普']:.3f} 对 {eq_row['夏普']:.3f}）", rp_row["夏普"] > eq_row["夏普"]),
        (f"   而且不是运气（重拼 {BOOTSTRAPS:,} 次，{share:.1%} 的情况更高，要至少 95%）", share >= 0.95),
        (f"2. 夏普高于各 1/3 掺国库券（{rp_row['夏普']:.3f} 对 {mt_row['夏普']:.3f}）", rp_row["夏普"] > mt_row["夏普"]),
        (f"   最大回撤也更小（{rp_row['最大回撤']:.1%} 对 {mt_row['最大回撤']:.1%}）",
         rp_row["最大回撤"] > mt_row["最大回撤"]),
        (f"3. 利率下降的年代夏普更高（{falling[1]:.3f} 对 {falling[0]:.3f}）", falling[1] > falling[0]),
        (f"   利率上升的年代夏普更高（{rising[1]:.3f} 对 {rising[0]:.3f}）", rising[1] > rising[0]),
    ]
    print("\n判断标准（计划里事先定的，要同时满足）：")
    for text, ok in checks:
        print(f"  {'✓' if ok else '✗'} {text}")
    passed = all(ok for _, ok in checks)
    print(f"\n结论：{'通过' if passed else '没通过，机器人保留各 1/3'}")


def references(returns, rf, equal, parity, matched, results):
    print(f"\n二、参考（只看，不参与决定；{EVAL[0]} 至 {EVAL[1]}，除注明外都和主检验一样）\n")
    static = pd.DataFrame([parity.loc[EVAL[0]].to_numpy()] * len(returns), index=returns.index, columns=ASSETS)
    variants = {
        "各 1/3": (equal, {}),
        "风险平价（主检验）": (parity, {}),
        "等风险贡献（考虑相关性）": (erc_weights(returns), {}),
        "固定比例：1975–1977 年定一次": (static, {}),
        "风险平价，成本 0.1%": (parity, {"cost": 0.001}),
        "风险平价，成本 0.2%": (parity, {"cost": 0.002}),
        "各 1/3，扣 ETF 管理费": (equal, {"fees": FEES}),
        "风险平价，扣 ETF 管理费": (parity, {"fees": FEES}),
    }
    rows = {name: summary(*portfolio(w, returns, rf, **kw), w, rf) for name, (w, kw) in variants.items()}
    print(pd.DataFrame(rows).T.to_string(formatters=TABLE_FORMAT))
    print(f"\n  固定比例是：{'，'.join(f'{NAMES[a]} {static.iloc[0][a]:.0%}' for a in ASSETS)}")

    start = "1980-01"  # 60 个月的窗口要到 1980 年才有比例，所以这几行从 1980 年开始比
    print(f"\n估计波动用几个月（{start} 至 {EVAL[1]}）：")
    base = sharpe(portfolio(equal, returns, rf, start=start)[0] - rf.loc[start:])
    for window in (12, 24, 36, 60):
        net, _ = portfolio(inverse_vol_weights(returns, window), returns, rf, start=start)
        print(f"  {window} 个月：夏普 {sharpe(net - rf.loc[start:]):.3f}（同期各 1/3 是 {base:.3f}）")

    print("\n几段危机（当年的收益）：")
    for year in ("2008", "2022"):
        parts = [f"{name} {(1 + results[name][0].loc[year]).prod() - 1:+.1%}" for name in results]
        print(f"  {year} 年：{'，'.join(parts)}")

    etf = etf_returns()
    etf_rf = rf.loc[etf.index]
    etf_parity = inverse_vol_weights(etf)
    etf_start = "2008-01"  # 计划里定的起点（2007-12 已经有比例，第一个月当作已经持有）
    assert etf_parity.loc[etf_start:].notna().all().all()
    etf_runs = {"各 1/3": equal_weights(etf), "风险平价": etf_parity,
                "各 1/3 掺国库券": risk_matched(etf, etf_parity)}
    etf_rows = {name: summary(*portfolio(w, etf, etf_rf, start=etf_start), w, etf_rf) for name, w in etf_runs.items()}
    print(f"\n直接用三只 ETF 的数据（{etf_start} 至 {etf.index[-1]}，价格里已经扣了管理费）：\n")
    print(pd.DataFrame(etf_rows).T.to_string(formatters=TABLE_FORMAT))


def etf_returns():
    """SPY、IEF、GLD 每月的总收益（复权价，月底对月底），到国库券数据的最后一个月为止。"""
    prices = pd.DataFrame({a: load_prices(t)["Close"] for a, t in ETFS.items()}).dropna()
    month_end = prices.groupby(prices.index.to_period("M")).last()
    return month_end.pct_change().dropna().loc[:EVAL[1]]


def plot(results, parity, rf):
    use_style()
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(10, 7.5), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
    styles = {"各 1/3": dict(color=INK_MUTED, linestyle="--"), "风险平价": dict(color=COLORS[1], linewidth=2),
              "各 1/3 掺国库券": dict(color=INK_SECONDARY, linewidth=1.2)}
    for name, (net, _) in results.items():
        wealth = (1 + net).cumprod()
        wealth.index = wealth.index.to_timestamp()
        top.plot(wealth, label=f"{name}：{wealth.iloc[-1]:,.0f} 美元", **{"linewidth": 1.5, **styles[name]})
    for a, b in RISING:
        for ax in (top, bottom):
            ax.axvspan(pd.Timestamp(a), pd.Timestamp(b) + pd.offsets.MonthEnd(0), color=INK_MUTED, alpha=0.12, lw=0)
    top.annotate("灰色：利率上升的年代", (0.99, 0.03), xycoords="axes fraction", ha="right", color=INK_SECONDARY,
                 fontsize=9)
    top.set_yscale("log")
    top.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:,.0f}" if y >= 1 else f"{y:g}"))
    top.set_ylabel("1 美元变成多少（对数刻度）")
    top.set_title(f"风险平价 vs 各 1/3（股票、国债、黄金），{EVAL[0][:4]}–{EVAL[1][:4]}", loc="left")
    top.legend(loc="upper left")

    weights = parity.loc[EVAL[0]:]
    weights.index = weights.index.to_timestamp()
    colors = [COLORS[0], COLORS[2], "#eda100"]
    bottom.stackplot(weights.index, *[weights[a] for a in ASSETS], colors=colors, alpha=0.85,
                     labels=[NAMES[a] for a in ASSETS])
    bottom.axhline(1 / 3, color="white", linewidth=0.8, linestyle=":")
    bottom.axhline(2 / 3, color="white", linewidth=0.8, linestyle=":")
    bottom.set_ylim(0, 1)
    bottom.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:.0%}"))
    bottom.set_ylabel("风险平价的比例")
    bottom.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, fontsize=9)  # 放在两张图中间，不压住颜色
    print()
    save_figure(fig, "research_risk_parity.png")


if __name__ == "__main__":
    main()

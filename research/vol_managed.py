"""研究：波动率择时——上个月越动荡，这个月股票拿得越少，能不能提高风险调整后的收益？

论文：Moreira 和 Muir（2017）。计划、文献和判断标准在 research/vol_managed_plan.md，
是看结果之前写好并提交的（git 提交 837c904）。

一、复现：照论文的做法算 1926-08 至 2015-04，和论文的数字对照，检查代码对不对。
二、主检验：比例只用当时之前的数据定，仓位最多 100%，扣成本，1936-08 至 2026-08，按计划里的三条标准判断。
三、参考：几个别的版本，只看，不参与决定。

计划里没写明、写代码时定的细节：
  - c 是两个标准差之比（都用 ddof=1）
  - 第一个评估月的调仓成本，按和上个月仓位的差算（上个月的仓位用同样的方法算），不当成从空仓买入
  - 月收益用 Kenneth French 按月文件里的市场超额收益，每月的方差用按天的文件算

运行（在项目根目录）：.venv/bin/python -m research.vol_managed
"""

import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter

from quant.data import load_prices
from quant.factors import load_daily_factors, load_french
from quant.metrics import equity_curve, max_drawdown, to_monthly
from quant.plot import COLORS, INK_MUTED, INK_SECONDARY, plt, save_figure, use_style
from quant.stats import regress

PAPER = ("1926-08", "2015-04")  # 论文的样本：论文没写明，按它的 1065 个月倒推
TRAIN_MONTHS = 120              # 前 120 个月只用来算 c
EVAL = ("1936-08", "2026-08")
SEGMENTS = [("1936-08", "1966-07"), ("1966-08", "1996-07"), ("1996-08", "2026-08")]
AFTER_PAPER = ("2015-05", "2026-08")
COST = 0.0005                   # 调仓成本：0.05% × 仓位变化量


def main():
    daily = load_daily_factors()
    monthly = load_french("three").join(load_french("momentum"))
    f, rf = monthly["Mkt-RF"], monthly["RF"]
    rv = realized_variance(daily["Mkt-RF"])
    pd.set_option("display.unicode.east_asian_width", True)

    replicate(f, rv)

    w = realtime_weights(f, rv, cap=1.0)
    assert str(w.index[TRAIN_MONTHS]) == EVAL[0]  # 前 120 个月只用来算 c，第 121 个月开始评估
    managed = after_cost(w, f, COST)
    primary_test(managed, w, f, rf)
    references(daily, monthly, rv, managed, w)
    spy_version(managed, w, f, rf)
    plot(managed, w, f, rf)


def realized_variance(daily_returns, per_22_days=False):
    """每个月的已实现方差：当月每天（收益 − 当月平均）² 加起来，论文的做法。

    per_22_days=True 时按当月交易日数折算成 22 天（1952 年以前周六也开盘，一个月的天数更多）。
    """
    groups = daily_returns.groupby(daily_returns.index.to_period("M"))
    rv = groups.apply(lambda r: ((r - r.mean()) ** 2).sum())
    return rv * 22 / groups.size() if per_22_days else rv


def paper_weights(f, rv, start, end):
    """论文原版的仓位：c 用这一段的全部数据定，让管理后的波动和市场一样大；不限杠杆。"""
    raw = (1 / rv.shift(1)).loc[start:end]  # 这个月的仓位用上个月的方差
    c = f.loc[start:end].std() / (f.loc[start:end] * raw).std()
    return c * raw


def realtime_weights(f, rv, cap=1.0, power=1.0):
    """实时版的仓位：每个月的 c 只用到上个月为止的数据算，仓位最多 cap 倍（None 表示不限）。

    power=1 按方差调整（论文的做法），power=0.5 按波动（标准差）调整。
    """
    raw = (1 / rv.shift(1) ** power).reindex(f.index).dropna()  # 这个月的仓位用上个月的方差
    f = f.loc[raw.index]
    c = (f.expanding().std() / (f * raw).expanding().std()).shift(1)  # 只用到上个月为止的数据
    return (c * raw).clip(upper=cap)


def after_cost(w, f, cost):
    """扣成本后的超额收益：仓位 × 市场超额收益 − 成本 × 仓位变化量。剩下的钱放国债，所以算的是超额收益。"""
    return w * f.loc[w.index] - cost * w.diff().abs()


def sharpe(excess):
    """夏普：超额收益（减掉国债利息）的月均值 ÷ 月标准差 × √12。"""
    return excess.mean() / excess.std() * np.sqrt(12)


def annual_return(total):
    """年化收益：按月复利。"""
    return (1 + total).prod() ** (12 / len(total)) - 1


def evaluate(excess, f, rf, period, w=None):
    """一个策略在一段时间里的表现。w 是仓位；一直持有不传 w，也不算 alpha（和自己比没有意义）。"""
    start, end = period
    ex = excess.loc[start:end]
    total = ex + rf.loc[start:end]  # 包括国债利息的总收益
    row = {"年化收益": annual_return(total), "夏普": sharpe(ex), "最大回撤": max_drawdown(total),
           "alpha": np.nan, "alpha 的 t 值": np.nan, "平均仓位": 1.0}
    if w is not None:
        res = regress(ex.rename("strategy"), f.loc[start:end].rename("market").to_frame(), robust=True)
        row.update({"alpha": res["coef"]["alpha"] * 12, "alpha 的 t 值": res["t"]["alpha"],
                    "平均仓位": w.loc[start:end].mean()})
    return row


def replicate(f, rv):
    start, end = PAPER
    w = paper_weights(f, rv, start, end)
    market = f.loc[start:end]
    managed = w * market
    res = regress(managed.rename("managed"), market.rename("market").to_frame(), robust=True)
    alpha = res["coef"]["alpha"] * 1200
    rows = [
        ("月数", f"{len(market)}", "1065"),
        ("alpha（年化，%）", f"{alpha:.2f}", "4.86"),
        ("alpha 的标准误", f"{res['stderr']['alpha'] * 1200:.2f}", "1.56"),
        ("beta", f"{res['coef']['market']:.2f}", "0.61"),
        ("R²", f"{res['r2']:.2f}", "0.37"),
        ("alpha ÷ 误差的波动（年化）", f"{res['coef']['alpha'] / res['resid_std'] * np.sqrt(12):.2f}", "0.33–0.34"),
        ("夏普：一直持有", f"{sharpe(market):.2f}", "0.42"),
        ("夏普：波动率择时", f"{sharpe(managed):.2f}", "0.51–0.52"),
        ("平均超额收益（年化，%）", f"{managed.mean() * 1200:.2f}", "9.47"),
        ("仓位每月平均变化", f"{w.diff().abs().mean():.2f}", "0.73"),
        ("仓位的中位数 / 75% / 90% / 99% 分位",
         " / ".join(f"{w.quantile(q):.2f}" for q in (0.5, 0.75, 0.9, 0.99)), "0.93 / 1.59 / 2.64 / 6.39"),
    ]
    print(f"一、复现论文（{start} 至 {end}；c 用全部数据定，不限杠杆，不扣成本）\n")
    print(pd.DataFrame([r[1:] for r in rows], index=[r[0] for r in rows], columns=["我们", "论文"]).to_string())
    ok = abs(alpha - 4.86) <= 0.5
    print(f"\n复现标准：alpha 在 4.86 ± 0.5 以内 → {'通过' if ok else '没通过，先找原因'}")
    print("\n论文原版的好处出在哪一段（夏普：波动率择时 对 一直持有）：")
    for a, b in [(start, "1936-07"), ("1936-08", end)]:
        print(f"  {a} 至 {b}：{sharpe(managed.loc[a:b]):.2f} 对 {sharpe(market.loc[a:b]):.2f}")


def primary_test(managed, w, f, rf):
    rows = {"一直持有": evaluate(f, f, rf, EVAL), "波动率择时": evaluate(managed, f, rf, EVAL, w)}
    print(f"\n二、主检验（{EVAL[0]} 至 {EVAL[1]}；c 只用当时之前的数据，仓位最多 100%，调仓成本 {COST:.2%}）\n")
    print(pd.DataFrame(rows).T.to_string(na_rep="—", formatters={
        "年化收益": "{:.1%}".format, "夏普": "{:.2f}".format, "最大回撤": "{:.0%}".format,
        "alpha": "{:+.2%}".format, "alpha 的 t 值": "{:.2f}".format, "平均仓位": "{:.2f}".format}))

    periods = SEGMENTS + [AFTER_PAPER]
    split = {p: (sharpe(f.loc[p[0]:p[1]]), sharpe(managed.loc[p[0]:p[1]])) for p in periods}
    print("\n分段的夏普：")
    for (start, end), (bh, vm) in split.items():
        note = "（论文数据之后）" if (start, end) == AFTER_PAPER else ""
        print(f"  {start} 至 {end}{note}：一直持有 {bh:.2f}，波动率择时 {vm:.2f}")

    print("\n几次大跌和反弹（市场超额收益 → 波动率择时的仓位和收益）：")
    for month in ["1987-10", "1987-12", "2008-10", "2009-03", "2020-03", "2020-04"]:
        print(f"  {month}：市场 {f[month]:+.1%} → 仓位 {w[month]:.2f}，收益 {managed[month]:+.1%}")
    a, b = "2007-11", "2009-02"  # 一直持有最大回撤的那一段
    cumulative = {name: (1 + r.loc[a:b] + rf.loc[a:b]).prod() - 1 for name, r in [("市场", f), ("波动率择时", managed)]}
    print(f"  {a} 至 {b} 累计：市场 {cumulative['市场']:+.0%}，波动率择时 {cumulative['波动率择时']:+.0%}")

    bh, vm = rows["一直持有"], rows["波动率择时"]
    checks = [
        (f"1. 整个评估期夏普更高（{vm['夏普']:.3f} 对 {bh['夏普']:.3f}）", vm["夏普"] > bh["夏普"]),
        (f"   最大回撤更小（{vm['最大回撤']:.0%} 对 {bh['最大回撤']:.0%}）", vm["最大回撤"] > bh["最大回撤"]),
        (f"   alpha 的 t 值大于 2（{vm['alpha 的 t 值']:.2f}）", vm["alpha 的 t 值"] > 2),
    ]
    for i, p in enumerate(SEGMENTS):
        s_bh, s_vm = split[p]
        checks.append((f"{'2.' if i == 0 else '  '} {p[0]} 至 {p[1]} 夏普更高（{s_vm:.3f} 对 {s_bh:.3f}）", s_vm > s_bh))
    s_bh, s_vm = split[AFTER_PAPER]
    checks.append((f"3. 论文数据之后夏普更高（{s_vm:.3f} 对 {s_bh:.3f}）", s_vm > s_bh))
    print("\n判断标准（计划里事先定的，要同时满足；夏普多显示一位小数，免得看起来一样却分了高低）：")
    for text, ok in checks:
        print(f"  {'✓' if ok else '✗'} {text}")
    passed = all(ok for _, ok in checks)
    print(f"\n结论：{'通过' if passed else '没通过，机器人不变'}")


def references(daily, monthly, rv, managed, w):
    f, rf = monthly["Mkt-RF"], monthly["RF"]
    variants = {"一直持有": (f, None), "主检验：实时、最多 1 倍、成本 0.05%": (managed, w)}
    for name, weights in [
        ("实时、不限杠杆", realtime_weights(f, rv, cap=None)),
        ("实时、最多 1.5 倍", realtime_weights(f, rv, cap=1.5)),
        ("按波动（1/σ）调整", realtime_weights(f, rv, power=0.5)),
        ("方差按 22 天折算", realtime_weights(f, realized_variance(daily["Mkt-RF"], per_22_days=True))),
    ]:
        variants[name] = (after_cost(weights, f, COST), weights)
    k = w.loc[EVAL[0]:EVAL[1]].mean()  # 公平的对照：平均仓位一样，但不择时
    variants[f"对照：一直拿 {k:.0%} 股票（主检验的平均仓位）"] = (k * f, pd.Series(k, index=f.index))
    variants["主检验，成本 0"] = (after_cost(w, f, 0.0), w)
    variants["主检验，成本 0.1%"] = (after_cost(w, f, 0.001), w)
    paper_w = paper_weights(f, rv, "1926-08", EVAL[1])
    variants["论文原版：全部数据定 c、不限杠杆、不扣成本"] = (paper_w * f.loc[paper_w.index], paper_w)

    rows = {}
    for name, (excess, weights) in variants.items():
        r = evaluate(excess, f, rf, EVAL, weights)
        rows[name] = {"夏普": r["夏普"], "最大回撤": r["最大回撤"], "alpha 的 t 值": r["alpha 的 t 值"],
                      "平均仓位": r["平均仓位"], "论文数据之后的夏普": sharpe(excess.loc[AFTER_PAPER[0]:AFTER_PAPER[1]])}
    print(f"\n三、参考（只看，不参与决定；{EVAL[0]} 至 {EVAL[1]}，除注明外都扣 {COST:.2%} 成本、最多 1 倍）\n")
    print(pd.DataFrame(rows).T.to_string(na_rep="—", formatters={
        "夏普": "{:.2f}".format, "最大回撤": "{:.0%}".format, "alpha 的 t 值": "{:.2f}".format,
        "平均仓位": "{:.2f}".format, "论文数据之后的夏普": "{:.2f}".format}))

    start, end = EVAL
    res = regress(managed.loc[start:end].rename("strategy"), monthly.loc[start:end, ["Mkt-RF", "SMB", "HML", "Mom"]],
                  robust=True)
    print(f"\n主检验再扣掉规模、价值、动量这几种侧重点：alpha {res['coef']['alpha'] * 12:+.2%}，t 值 {res['t']['alpha']:.2f}")


def spy_version(managed, w, f, rf):
    """用 SPY 每天的数据做同样的事，最接近机器人会怎么做。SPY 1993 年才有，前 120 个月只用来算 c。"""
    daily = load_prices("SPY")["Close"].pct_change().dropna()
    f_spy = (to_monthly(daily) - rf).dropna()  # SPY 每月的超额收益，到国债数据的最后一个月为止
    w_spy = realtime_weights(f_spy, realized_variance(daily), cap=1.0)
    period = (str(w_spy.index[TRAIN_MONTHS]), str(f_spy.index[-1]))
    m_spy = after_cost(w_spy, f_spy, COST)
    rows = {
        "SPY 一直持有": evaluate(f_spy, f_spy, rf, period),
        "SPY 波动率择时": evaluate(m_spy, f_spy, rf, period, w_spy),
        "主检验（全市场数据）同一段": evaluate(managed, f, rf, period, w),
    }
    print(f"\n用 SPY 每天的数据（{period[0]} 至 {period[1]}，最多 1 倍，扣 {COST:.2%} 成本）\n")
    print(pd.DataFrame(rows).T.drop(columns=["alpha"]).to_string(na_rep="—", formatters={
        "年化收益": "{:.1%}".format, "夏普": "{:.2f}".format, "最大回撤": "{:.0%}".format,
        "alpha 的 t 值": "{:.2f}".format, "平均仓位": "{:.2f}".format}))
    crisis = pd.period_range("2007-10", "2009-06", freq="M")
    rest = [r.loc[period[0]:period[1]].drop(crisis) for r in (m_spy, f_spy)]
    print(f"\n去掉 2007-10 至 2009-06 的金融危机：SPY 波动率择时夏普 {sharpe(rest[0]):.2f}，一直持有 {sharpe(rest[1]):.2f}")


def plot(managed, w, f, rf):
    start, end = EVAL
    use_style()
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(10, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    for excess, name, style in [(f, "一直持有", dict(color=INK_MUTED, linestyle="--")),
                                (managed, "波动率择时（只用当时的数据、不借钱）", dict(color=COLORS[0], linewidth=2))]:
        wealth = equity_curve(excess.loc[start:end] + rf.loc[start:end])
        wealth.index = wealth.index.to_timestamp()
        top.plot(wealth, label=f"{name}：{wealth.iloc[-1]:,.0f} 美元", **{"linewidth": 1.5, **style})
    top.set_yscale("log")
    top.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:,.0f}" if y >= 1 else f"{y:g}"))
    top.set_ylabel("1 美元变成多少（对数刻度，含国债利息）")
    top.set_title(f"波动率择时 vs 一直持有，{start[:4]}–{end[:4]}", loc="left")
    top.legend(loc="upper left")

    paper_end = pd.Timestamp(f"{AFTER_PAPER[0]}-01")
    for ax in (top, bottom):
        ax.axvline(paper_end, color=INK_MUTED, linewidth=1, linestyle=":")
    top.annotate("论文的数据到这里为止", (paper_end, 0.02), xycoords=("data", "axes fraction"), xytext=(-6, 0),
                 textcoords="offset points", ha="right", color=INK_SECONDARY, fontsize=9)

    weight = w.loc[start:end]
    weight.index = weight.index.to_timestamp()
    bottom.fill_between(weight.index, weight, step="post", color=COLORS[0], alpha=0.25, linewidth=0)
    bottom.step(weight.index, weight, where="post", color=COLORS[0], linewidth=0.8)
    bottom.set_ylim(0, 1.05)
    bottom.set_ylabel("股票仓位")
    print()
    save_figure(fig, "research_vol_managed.png")


if __name__ == "__main__":
    main()

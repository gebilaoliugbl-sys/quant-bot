"""组合：同时持有几样资产，定期调回目标比例。"""

import pandas as pd


def rebalanced_returns(returns: pd.DataFrame, weights: dict) -> pd.Series:
    """每月第一个交易日把各资产调回目标比例，月内随行情自然漂移，返回组合的日收益。

    returns 的每一列是一样资产的日收益，weights 是 {列名: 比例}，比例加起来为 1。
    调仓的成本很小，这里不算。
    """
    w = pd.Series(weights)
    months = []
    for _, month in returns[w.index].groupby(returns.index.to_period("M")):
        value = (1 + month).cumprod() @ w  # 月初投 1 块钱，这个月每天收盘时组合值多少
        months.append(value.pct_change().fillna(value.iloc[0] - 1))
    return pd.concat(months)


def monthly_portfolio(returns: pd.DataFrame, targets: pd.DataFrame, cost_bps: float = 5.0) -> pd.Series:
    """每月第一个交易日按 targets 调仓，月内随行情漂移，返回组合的日收益（已扣调仓成本）。

    returns：每列一样资产的日收益，可以有一列现金（比如国债利息）
    targets：每个月一行目标比例，索引是那个月的第一个交易日，列和 returns 一样，每行加起来为 1。
             某个月的比例只能用上个月底以前的数据来定，否则就是偷看未来
    cost_bps：调仓金额每 100% 付出的成本，单位基点。第一个月从空仓建仓，也算一次调仓
    """
    weights = pd.Series(0.0, index=returns.columns)  # 调仓前各部分的实际比例
    months = []
    for _, month in returns.groupby(returns.index.to_period("M")):
        target = targets.loc[month.index[0], returns.columns]
        cost = (target - weights).abs().sum() * cost_bps / 10_000
        growth = (1 + month).cumprod()
        value = growth @ target                      # 月初投 1 块钱，这个月每天收盘时组合值多少
        daily = value.pct_change()
        daily.iloc[0] = value.iloc[0] - 1 - cost     # 调仓成本记在第一天
        months.append(daily)
        weights = growth.iloc[-1] * target / value.iloc[-1]  # 月底漂移后的比例，下个月调仓时和目标比
    return pd.concat(months)

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

"""最简单的向量化回测：给定每天收盘时定下的目标仓位，算出策略每天的收益。"""

import pandas as pd


def run_backtest(close: pd.Series, signal: pd.Series, cost_bps: float = 5.0) -> pd.DataFrame:
    """按 signal 持仓，返回每天的仓位、标的收益、交易成本和策略收益。

    signal[t] 是第 t 天收盘时、只用当时已知的信息定下的目标仓位
    （1 = 满仓，0 = 空仓拿现金）。它最早只能吃到第 t+1 天的涨跌，
    所以实际仓位是 signal 往后挪一天。这里假设按第 t 天的收盘价成交，
    现实中可以用收盘竞价单近似。

    cost_bps 是仓位每变动 100% 付出的成本，单位是基点（1bp = 0.01%），
    包括佣金、买卖价差和滑点。现金部分不计利息。
    """
    asset = close.pct_change().fillna(0.0)
    position = signal.shift(1).fillna(0.0)
    turnover = position.diff().abs().fillna(position.abs())
    cost = turnover * cost_bps / 10_000
    return pd.DataFrame({
        "position": position,
        "asset": asset,
        "cost": cost,
        "strategy": position * asset - cost,
    })

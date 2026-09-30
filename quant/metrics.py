"""绩效指标。输入都是日收益率序列，0.01 表示当天涨 1%。"""

import numpy as np
import pandas as pd

TRADING_DAYS = 252  # 美股一年大约 252 个交易日


def equity_curve(returns: pd.Series) -> pd.Series:
    """1 块钱按这串日收益率复利下去的净值。"""
    return (1 + returns).cumprod()


def cagr(returns: pd.Series) -> float:
    """年化收益：总收益折算成平均每年复利多少。"""
    years = len(returns) / TRADING_DAYS
    return equity_curve(returns).iloc[-1] ** (1 / years) - 1


def annual_volatility(returns: pd.Series) -> float:
    """年化波动：日收益的标准差乘以 sqrt(252)，衡量净值抖得多厉害。"""
    return returns.std() * np.sqrt(TRADING_DAYS)


def sharpe_ratio(returns: pd.Series) -> float:
    """夏普比率：每承担一单位波动换来多少收益。这里简化成无风险利率为 0。"""
    return returns.mean() / returns.std() * np.sqrt(TRADING_DAYS)


def drawdown(returns: pd.Series) -> pd.Series:
    """每天的回撤：净值比之前的最高点（包括起始的 1 块钱）低了多少。"""
    equity = equity_curve(returns)
    return equity / equity.cummax().clip(lower=1.0) - 1


def max_drawdown(returns: pd.Series) -> float:
    """最大回撤：历史上从高点跌到低点最深的一次。"""
    return drawdown(returns).min()


def to_monthly(returns):
    """日收益换成月收益：一个月里每天的 (1 + 收益) 连乘，再减 1。索引变成月份。"""
    return (1 + returns).groupby(returns.index.to_period("M")).prod() - 1


def summary(returns: pd.Series) -> pd.Series:
    return pd.Series({
        "年化收益": cagr(returns),
        "年化波动": annual_volatility(returns),
        "夏普比率": sharpe_ratio(returns),
        "最大回撤": max_drawdown(returns),
    })

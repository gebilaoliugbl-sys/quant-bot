"""算出把账户调回目标比例要下哪些单。纯计算，不联网，方便单独检查。"""

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class Order:
    symbol: str
    side: str                     # "buy" 或 "sell"
    amount: float                 # 大约多少美元
    qty: Optional[float] = None   # 卖出时按股数下单


def plan_orders(equity, holdings, weights, cash_buffer=0.01, min_trade=100.0):
    """返回先卖后买的订单列表。

    equity：账户总值（现金 + 持仓市值），美元
    holdings：{代码: (持有股数, 当前价格)}，只包括 weights 里的代码
    weights：{代码: 目标比例}，加起来为 1
    cash_buffer：留一点现金不投，防止下单时价格变动导致钱不够
    min_trade：调整金额小于这个数就不做，省成本
    """
    investable = equity * (1 - cash_buffer)
    orders = []
    for symbol, weight in weights.items():
        qty, price = holdings.get(symbol, (0.0, 0.0))
        diff = investable * weight - qty * price
        if abs(diff) < min_trade:
            continue
        if diff > 0:
            orders.append(Order(symbol, "buy", round(diff, 2)))
        else:
            sell_qty = math.floor(min(qty, -diff / price) * 1e6) / 1e6  # 往下取到 6 位小数
            orders.append(Order(symbol, "sell", -diff, sell_qty))
    return sorted(orders, key=lambda o: o.side != "sell")

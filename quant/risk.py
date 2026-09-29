"""下单前的风控检查：程序出 bug 时的刹车。纯计算，不联网，方便单独测试。"""

MAX_ORDER_FRACTION = 0.40  # 单笔不能超过账户总值的 40%（正常建仓每样 33%）
MAX_TOTAL_FRACTION = 1.00  # 一次运行的买卖总额不能超过账户总值


def check_orders(orders, equity, allowed_symbols):
    """返回发现的问题；空列表表示通过。"""
    if equity <= 0:
        return ["账户总值不是正数，数据可能有问题"]
    problems = []
    for o in orders:
        if o.symbol not in allowed_symbols:
            problems.append(f"{o.symbol} 不在允许交易的名单里")
        if o.amount > equity * MAX_ORDER_FRACTION:
            problems.append(f"{o.symbol} 这一单 {o.amount:,.0f} 美元，超过账户总值的 {MAX_ORDER_FRACTION:.0%}")
        if o.side == "sell" and not o.qty:
            problems.append(f"{o.symbol} 的卖单没有股数")
    total = sum(o.amount for o in orders)
    if total > equity * MAX_TOTAL_FRACTION:
        problems.append(f"这次一共要买卖 {total:,.0f} 美元，超过账户总值的 {MAX_TOTAL_FRACTION:.0%}")
    return problems

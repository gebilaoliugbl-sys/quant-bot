"""查看模拟账户：总值、今天的盈亏、每样持仓、最近的订单。只读，不下单。

运行：.venv/bin/python paper_status.py

几个词：
  买入均价：你买进来时平均每股花了多少钱
  浮动盈亏：还没卖，按现在的价格算，账面上赚了或亏了多少
  今天盈亏：账户总值和昨天收盘时比，变了多少
"""

import pandas as pd

from quant.alpaca import PaperBroker

STATUS = {
    "new": "已提交，等成交", "accepted": "已接受，等开盘", "pending_new": "提交中",
    "partially_filled": "部分成交", "filled": "已成交", "canceled": "已取消",
    "expired": "已过期", "rejected": "被拒绝",
}


def main():
    broker = PaperBroker()
    account = broker.account()
    equity, last_close = float(account["equity"]), float(account["last_equity"])
    print(f"账户总值 {float(account['equity']):,.2f} 美元，其中现金 {float(account['cash']):,.2f} 美元")
    print(f"今天盈亏 {equity - last_close:+,.2f} 美元（{(equity - last_close) / last_close:+.2%}）\n")

    positions = broker.positions()
    if positions:
        print("代码      持有股数    买入均价    现在价格          市值     占比       浮动盈亏")
        for p in positions:
            value = float(p["market_value"])
            print(f"{p['symbol']:<6} {float(p['qty']):>10.4f} {float(p['avg_entry_price']):>11.2f} "
                  f"{float(p['current_price']):>11.2f} {value:>13,.2f} {value / equity:>8.1%} "
                  f"{float(p['unrealized_pl']):>+11,.2f}（{float(p['unrealized_plpc']):+.2%}）")
    else:
        print("还没有持仓")

    print("\n最近的订单（英国时间）：")
    for o in broker.recent_orders():
        when = pd.Timestamp(o["submitted_at"]).tz_convert("Europe/London").strftime("%m-%d %H:%M")
        side = "买入" if o["side"] == "buy" else "卖出"
        size = f"{float(o['notional']):,.2f} 美元" if o.get("notional") else f"{float(o['qty']):.4f} 股"
        line = f"  {when}  {side} {o['symbol']:<4} {size:>14}  {STATUS.get(o['status'], o['status'])}"
        if float(o.get("filled_qty") or 0) > 0:
            line += f"，成交 {float(o['filled_qty']):.4f} 股，均价 {float(o['filled_avg_price']):.2f}"
        print(line)


if __name__ == "__main__":
    main()

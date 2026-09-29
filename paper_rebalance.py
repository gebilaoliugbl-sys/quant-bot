"""模拟盘：把 Alpaca 模拟账户调成股票 SPY、国债 IEF、黄金 GLD 各 1/3，每月调一次。

三种运行方式：
  .venv/bin/python paper_rebalance.py            # 演练：只打印打算下的单，不下单
  .venv/bin/python paper_rebalance.py --submit   # 下单到模拟账户（用的是假钱）
  .venv/bin/python paper_rebalance.py --auto     # 每天定时运行用，见下面

--auto：这个月已经检查过（调过仓，或者判断不用调）就直接退出；
还没检查过，就照常计算，需要调仓就直接下单。所以每天跑一次，
这个月里 Mac 哪天先醒着，就在哪天完成这个月的调仓。

休市时下的单会排队，到下个交易日开盘才成交。

下单前的风控检查（任何一条不通过都不下单）：
  金额：单笔、总额都有上限，见 quant/risk.py
  频率：每月最多交易一次，确实要再交易加 --force
  紧急停止：~/quant-bot 里有一个叫 STOP 的文件，就一律不下单

记录：每笔单子记在 ~/quant-bot/logs/paper_orders.csv，
每次检查的结果记在 ~/quant-bot/logs/paper_runs.csv（位置见 quant/paths.py）。
"""

import argparse
import csv
from datetime import datetime, timezone

from quant.alpaca import PaperBroker
from quant.notify import notify
from quant.paths import LOG_DIR, STOP_FILE
from quant.rebalance import plan_orders
from quant.risk import check_orders

WEIGHTS = {"SPY": 1 / 3, "IEF": 1 / 3, "GLD": 1 / 3}
CASH_BUFFER = 0.01  # 留 1% 现金不投，防止下单时价格变动导致钱不够
LOG_FILE = LOG_DIR / "paper_orders.csv"
RUN_FILE = LOG_DIR / "paper_runs.csv"
RUN_TITLES = {"no_trade": "月度检查：不用交易", "blocked": "被风控拦下，没有下单", "traded": "调仓完成"}


def main():
    parser = argparse.ArgumentParser(description="把模拟账户调回目标比例")
    parser.add_argument("--submit", action="store_true", help="真的把单子发到模拟账户")
    parser.add_argument("--auto", action="store_true", help="定时运行：本月检查过就退出，否则检查并下单")
    parser.add_argument("--force", action="store_true", help="这个月已经交易过，仍然要再交易")
    args = parser.parse_args()
    submit = args.submit or args.auto

    if args.auto:
        print(f"==== {datetime.now():%Y-%m-%d %H:%M} 自动运行 ====")
        if checked_this_month():
            print("这个月已经检查过了，下个月再来")
            return

    broker = PaperBroker()
    account = broker.account()
    equity = float(account["equity"])
    print(f"模拟账户总值 {equity:,.2f} 美元，其中现金 {float(account['cash']):,.2f} 美元\n")

    pending = broker.open_orders()
    if pending:
        print(f"还有 {len(pending)} 笔单子没成交（可能在排队等开盘）。等它们处理完再运行，避免重复下单")
        if args.auto:
            notify("量化机器人：有单子没成交", f"还有 {len(pending)} 笔单子在等成交，今天先不动")
        return

    positions = {p["symbol"]: p for p in broker.positions()}
    holdings = {s: (float(p["qty"]), float(p["current_price"])) for s, p in positions.items() if s in WEIGHTS}
    others = sorted(set(positions) - set(WEIGHTS))
    if others:
        print(f"注意：账户里还有不归这个程序管的持仓 {', '.join(others)}，不会动它们\n")

    print("代码   现在市值（美元）   现在占比   目标占比")
    for symbol, weight in WEIGHTS.items():
        qty, price = holdings.get(symbol, (0.0, 0.0))
        print(f"{symbol:<6} {qty * price:>16,.2f} {qty * price / equity:>10.1%} {weight * (1 - CASH_BUFFER):>10.1%}")
    print(f"现金   {'':>16} {'':>10} {CASH_BUFFER:>10.1%}")

    orders = plan_orders(equity, holdings, WEIGHTS, cash_buffer=CASH_BUFFER)
    if not orders:
        print("\n各部分都接近目标比例，这次不用交易")
        if submit:
            record_run("no_trade", "各部分都接近目标比例")
        return
    print("\n打算下的单：")
    for o in orders:
        if o.side == "sell":
            print(f"  卖出 {o.symbol}：{o.qty} 股（约 {o.amount:,.2f} 美元）")
        else:
            print(f"  买入 {o.symbol}：{o.amount:,.2f} 美元")

    problems = check_orders(orders, equity, WEIGHTS)
    if traded_this_month() and not args.force:
        problems.append("这个月已经交易过了（每月最多一次）。确实要再交易，加 --force")
    if STOP_FILE.exists():
        problems.append(f"发现紧急停止文件 {STOP_FILE}，删掉它才能恢复交易")
    if problems:
        print("\n风控检查没通过，不下单：")
        for p in problems:
            print(f"  - {p}")
        if submit:
            record_run("blocked", "；".join(problems))
        return
    print("\n风控检查：通过")

    if not submit:
        print("\n这是演练，没有下单。确认没问题后加上 --submit 再运行")
        return

    for symbol in WEIGHTS:
        if not broker.asset(symbol)["fractionable"]:
            raise SystemExit(f"{symbol} 不支持买小数股，这个程序暂时处理不了")
    market_open = broker.clock()["is_open"]
    if not market_open:
        print("\n现在美股休市，单子会排队到下个交易日开盘成交")

    print("\n下单结果：")
    for o in orders:
        if o.side == "buy":
            result = broker.submit_market_order(o.symbol, "buy", notional=o.amount)
        else:
            result = broker.submit_market_order(o.symbol, "sell", qty=o.qty)
        print(f"  {o.symbol} {o.side}：订单号 {result['id']}，状态 {result['status']}")
        append_row(LOG_FILE, ["time_utc", "symbol", "side", "amount_usd", "qty", "order_id", "status"],
                   [now_utc(), o.symbol, o.side, f"{o.amount:.2f}", o.qty or "", result["id"], result["status"]])
    summary = "；".join(f"{'卖出' if o.side == 'sell' else '买入'} {o.symbol} {o.amount:,.0f} 美元" for o in orders)
    if not market_open:
        summary += "（现在休市，开盘后成交）"
    record_run("traded", summary)
    print(f"\n已记到 {LOG_FILE}")


def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def rows_this_month(path):
    """日志文件里这个月（按世界标准时间）的记录。"""
    if not path.exists():
        return []
    this_month = datetime.now(timezone.utc).strftime("%Y-%m")
    with path.open() as f:
        return [row for row in csv.DictReader(f) if row["time_utc"].startswith(this_month)]


def traded_this_month():
    return bool(rows_this_month(LOG_FILE))


def checked_this_month():
    """这个月有没有完成过一次检查：调过仓，或者判断不用调。被风控拦下的不算，第二天会再试。"""
    return any(row["result"] in ("no_trade", "traded") for row in rows_this_month(RUN_FILE))


def record_run(result, detail=""):
    """记下这次检查的结果，同时发通知告诉你。"""
    append_row(RUN_FILE, ["time_utc", "result", "detail"], [now_utc(), result, detail])
    notify(f"量化机器人：{RUN_TITLES[result]}", detail)


def append_row(path, header, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with path.open("a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(header)
        writer.writerow(row)


def run():
    """入口：运行 main。出错时先发通知，再照常报错，错误详情会留在日志里。"""
    try:
        main()
    except SystemExit as e:
        if e.code not in (None, 0):  # 带着错误信息退出，比如找不到密钥、密钥被拒
            notify("量化机器人出错", str(e.code))
        raise
    except Exception as e:
        notify("量化机器人出错", f"{type(e).__name__}：{e}")
        raise


if __name__ == "__main__":
    run()

"""Alpaca 模拟账户（paper trading）的最小客户端。

只连模拟盘：地址写死成 paper-api，这个程序不可能碰到真钱账户。
密钥从 ~/quant-bot/.env 读取（见 quant/paths.py），不写在代码里。
"""

import warnings

# macOS 自带的 Python 用的是旧版 SSL 库，urllib3 会打印一条无害的警告
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

import requests  # noqa: E402

from quant.paths import ENV_FILE  # noqa: E402

PAPER_URL = "https://paper-api.alpaca.markets"
KEY_NAMES = ("ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY")


def load_keys():
    """从 .env 读出密钥。"""
    if not ENV_FILE.exists():
        raise SystemExit(f"找不到 {ENV_FILE}：运行 bash scheduler/install.sh 会把项目里的 .env 挪过去")
    keys = {}
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            keys[name.strip()] = value.strip()
    missing = [k for k in KEY_NAMES if not keys.get(k)]
    if missing:
        raise SystemExit(f".env 里缺少：{', '.join(missing)}")
    return keys


class PaperBroker:
    def __init__(self):
        keys = load_keys()
        self.session = requests.Session()
        self.session.headers.update({
            "APCA-API-KEY-ID": keys["ALPACA_API_KEY_ID"],
            "APCA-API-SECRET-KEY": keys["ALPACA_API_SECRET_KEY"],
        })

    def _request(self, method, path, **kwargs):
        response = self.session.request(method, PAPER_URL + path, timeout=15, **kwargs)
        if response.status_code in (401, 403):
            raise SystemExit("Alpaca 拒绝了密钥：检查 .env 里填的是不是模拟账户（Paper）的密钥")
        if not response.ok:
            raise RuntimeError(f"Alpaca 返回错误 {response.status_code}：{response.text}")
        return response.json()

    def account(self):
        return self._request("GET", "/v2/account")

    def clock(self):
        return self._request("GET", "/v2/clock")

    def asset(self, symbol):
        return self._request("GET", f"/v2/assets/{symbol}")

    def positions(self):
        return self._request("GET", "/v2/positions")

    def open_orders(self):
        return self._request("GET", "/v2/orders", params={"status": "open"})

    def recent_orders(self, limit=10):
        """最近的订单，不管成交没成交，新的在前。"""
        return self._request("GET", "/v2/orders", params={"status": "all", "limit": limit, "direction": "desc"})

    def submit_market_order(self, symbol, side, notional=None, qty=None):
        """当天有效的市价单。买入按金额（notional），卖出按股数（qty，可以是小数）。"""
        order = {"symbol": symbol, "side": side, "type": "market", "time_in_force": "day"}
        if notional is not None:
            order["notional"] = f"{notional:.2f}"
        else:
            order["qty"] = f"{qty:.6f}"
        return self._request("POST", "/v2/orders", json=order)

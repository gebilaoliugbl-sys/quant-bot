"""行情数据：从 Yahoo Finance 下载日线，缓存到 data/ 目录。"""

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_prices(ticker: str, start: str = "1990-01-01", refresh: bool = False) -> pd.DataFrame:
    """返回 ticker 的日线 OHLCV，已按拆股和分红复权。

    复权后的 Close 已经把分红算进去，相当于分红再投资的总回报。
    第一次调用会下载并存成 data/<ticker>.csv，之后直接读缓存；
    refresh=True 时重新下载，更新到最新的交易日。
    """
    path = DATA_DIR / f"{ticker}.csv"
    if path.exists() and not refresh:
        return pd.read_csv(path, index_col="Date", parse_dates=True)

    import yfinance as yf  # 只有下载时才需要

    df = yf.download(ticker, start=start, auto_adjust=True, progress=False, multi_level_index=False)
    if df.empty:
        raise RuntimeError(f"没有下载到 {ticker} 的数据，检查代码拼写或网络")

    # 当天的 K 线收盘前还在变，一律去掉，只用已经收盘的交易日
    today_ny = pd.Timestamp.now(tz="America/New_York").normalize().tz_localize(None)
    df = df[df.index < today_ny]

    DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(path)
    return df

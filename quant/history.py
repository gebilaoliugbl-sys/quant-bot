"""1975 年以来股票、国债、黄金、国库券的月收益，给 ETF 上市以前的年代做回测用。

机器人用的三只 ETF 上市得都比较晚（GLD 2004 年才有）。只用它们的数据，样本只有二十来年，
而且大半落在国债的大牛市里。这里用公开数据把三样东西补到 1975 年：

  stocks：美国全市场（Kenneth French 的 Mkt-RF + RF），代替 SPY
  bonds：7 年期和 10 年期国债各一半，用美联储公布的利率（FRED 的 DGS7、DGS10）算出每月收益，代替 IEF
  gold：伦敦金每天下午的定盘价，取每月最后一个，代替 GLD
  rf：一个月期国库券（Kenneth French 的 RF）

为什么从 1975 年开始：1974 年底以前美国人不能合法持有黄金，之前的金价涨幅普通人拿不到。

和 ETF 对照过重叠的年份，每月收益的相关系数：股票 0.99，国债 0.99，黄金 0.98。
这些都是指数本身的收益，没有扣 ETF 的管理费（每年 SPY 0.09%、IEF 0.15%、GLD 0.40%）。

伦敦金价的再分发需要授权，官网又不让程序下载，这里用的是 GitHub 上的非官方副本
（和另一份副本逐日核对过，完全一致）。只下载到本地的 data/ 自己研究用，不进仓库。
下载后缓存在 data/，要更新就删掉 data/fred_*.csv 和 data/gold_lbma.csv。
"""

import pandas as pd

from quant.data import DATA_DIR
from quant.factors import load_french

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
GOLD_URL = "https://raw.githubusercontent.com/tomelam/PortfolioAnalyzer/main/data/reference/gold_lbma_usd_daily.csv"
START = "1975-01"


def load_history(start: str = START) -> pd.DataFrame:
    """每月的总收益（小数，0.01 表示 1%），列是 stocks、bonds、gold、rf，索引是月份。"""
    french = load_french("three")
    df = pd.DataFrame({
        "stocks": french["Mkt-RF"] + french["RF"],
        "bonds": treasury_returns(),
        "gold": gold_returns(),
        "rf": french["RF"],
    }).dropna().loc[start:]
    if not df.index.equals(pd.period_range(df.index[0], df.index[-1], freq="M")):
        raise ValueError("月份不连续，数据有缺口")
    return df


def treasury_returns() -> pd.Series:
    """7 年期和 10 年期国债各一半，每月的总收益。

    每个月底按当时的利率买一只"平价债"（价格 1、票息等于当时的利率），一个月后按新的利率重新估价：
    收益 = 价格变化 + 这一个月的利息。重新估价时，债券的期限少了一个月，所以用略短一点的期限对应的利率
    （在 5、7、10 年期利率之间按直线插出来），这样才和真实的国债基金对得上。
    """
    rates = pd.DataFrame({n: month_end(load_fred(f"DGS{n}")) for n in (5, 7, 10)}).dropna() / 100
    ten = par_bond_return(rates[10], rates[7], 10, 7)
    seven = par_bond_return(rates[7], rates[5], 7, 5)
    return (ten + seven) / 2


def par_bond_return(rate: pd.Series, shorter_rate: pd.Series, years: float, shorter_years: float) -> pd.Series:
    """期限 years 年的平价债持有一个月的收益。shorter_rate 是期限 shorter_years 年的利率，用来插值。"""
    coupon = rate.shift(1)                                                    # 上个月底买入，票息就是当时的利率
    new_rate = rate - (rate - shorter_rate) * (1 / 12) / (years - shorter_years)  # 剩下 years - 1/12 年的利率
    discount = (1 + new_rate / 2) ** (-2 * (years - 1 / 12))                  # 美国国债每半年付一次息
    price = coupon / new_rate * (1 - discount) + discount                     # 一个月后的价格（买入时是 1）
    return (price - 1 + coupon / 12).dropna()                                 # 价格变化 + 一个月的利息


def gold_returns() -> pd.Series:
    """伦敦金每天下午的定盘价（美元），取每月最后一个，算每月涨跌。"""
    path = DATA_DIR / "gold_lbma.csv"
    if not path.exists():
        download(GOLD_URL, path)
    price = pd.read_csv(path, index_col=0, parse_dates=True).iloc[:, 0]
    return month_end(price).pct_change().dropna()


def load_fred(series_id: str) -> pd.Series:
    """FRED 的一个日度序列，缓存成 data/fred_<id>.csv。节假日没有数，跳过。"""
    path = DATA_DIR / f"fred_{series_id}.csv"
    if not path.exists():
        download(FRED_URL.format(series_id), path)
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return pd.to_numeric(df.iloc[:, 0], errors="coerce").dropna()


def month_end(daily: pd.Series) -> pd.Series:
    """每个月最后一个有数据的那天的值，索引是月份。

    最后一个月如果还没过完（数据停在月底一周以前），就去掉，免得把月中的价格当成月底。
    """
    daily = daily.dropna()
    last = daily.groupby(daily.index.to_period("M")).last()
    if daily.index[-1] < last.index[-1].to_timestamp(how="end") - pd.Timedelta(days=7):
        last = last.iloc[:-1]
    return last


def download(url: str, path) -> None:
    import requests  # 只有下载时才需要

    response = requests.get(url, timeout=60)
    response.raise_for_status()
    DATA_DIR.mkdir(exist_ok=True)
    path.write_text(response.text)

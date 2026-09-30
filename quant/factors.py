"""学术界公开的因子数据：Kenneth French 教授的数据库，1926 年至今，按月。

每个因子是两篮子股票的收益差，比如 SMB = 小公司那篮子 - 大公司那篮子。
每个时期用的都是当时所有上市的股票（包括后来退市的），没有幸存者偏差。
下载后缓存到 data/，要更新就删掉 data/ff_*.csv。

  Mkt-RF：整个股市比一个月期国债多赚多少（市场）
  SMB：小公司减大公司（规模，Small Minus Big）
  HML：便宜的公司减贵的公司，按股价相对账面价值算（价值，High Minus Low）
  Mom：过去一年涨得好的减涨得差的（动量）
  RF：一个月期国债的收益
"""

import io
import zipfile

import pandas as pd

from quant.data import DATA_DIR

BASE_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
FILES = {"three": "F-F_Research_Data_Factors_CSV.zip", "momentum": "F-F_Momentum_Factor_CSV.zip"}


def load_factors() -> pd.DataFrame:
    """市场、规模、价值、动量四个因子加上国债收益，按月，收益是小数（0.01 表示 1%）。"""
    return load_french("three").join(load_french("momentum"), how="inner")


def load_french(name: str) -> pd.DataFrame:
    """下载并解析一个数据文件的按月部分，缓存成 data/ff_<name>.csv。"""
    path = DATA_DIR / f"ff_{name}.csv"
    if path.exists():
        df = pd.read_csv(path, index_col=0)
        df.index = pd.PeriodIndex(df.index, freq="M")
        return df

    import requests  # 只有下载时才需要

    response = requests.get(BASE_URL + FILES[name], timeout=30)
    response.raise_for_status()
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    lines = archive.read(archive.namelist()[0]).decode("latin-1").splitlines()

    # 前面是说明文字；以逗号开头的第一行是表头，下面是按月的数据（日期写成 192607），
    # 遇到第一行不是这种日期的，按月的部分就结束了，后面是按年的汇总
    start = next(i for i, line in enumerate(lines) if line.startswith(","))
    columns = [c.strip() for c in lines[start].split(",")[1:]]
    months, values = [], []
    for line in lines[start + 1:]:
        cells = [c.strip() for c in line.split(",")]
        if not (len(cells[0]) == 6 and cells[0].isdigit()):
            break
        months.append(f"{cells[0][:4]}-{cells[0][4:]}")
        values.append([float(v) for v in cells[1:]])

    df = pd.DataFrame(values, columns=columns, index=pd.PeriodIndex(months, freq="M")) / 100  # 百分数换成小数
    if (df <= -0.9999).any().any():
        raise ValueError(f"{FILES[name]} 里有缺失值标记（-99.99），需要单独处理")
    DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(path)
    return df

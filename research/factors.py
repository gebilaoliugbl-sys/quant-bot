"""研究：股票市场上长期存在的几种收益来源（因子），真的有效吗？一直有效吗？

数据：Kenneth French 数据库，1927 年至今按月，没有幸存者偏差（见 quant/factors.py）。

一、近百年的证据：每个因子平均每年多赚多少、t 值多少；
    再按学术论文公开发表的年份分成前后两段，看公开之后还剩多少。
    规模：Banz（1981）；价值：Fama 和 French（1992）；动量：Jegadeesh 和 Titman（1993）。
二、给基金做体检：用四个因子回归 SPY（大公司）、IWM（小公司）、QQQ（以科技股为主），
    看它们各自偏向哪种因子，和直觉对不对得上。

运行（在项目根目录）：.venv/bin/python -m research.factors
"""

import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter

from quant.data import load_prices
from quant.factors import load_factors
from quant.metrics import to_monthly
from quant.plot import COLORS, INK_SECONDARY, label_line_end, plt, save_figure, use_style
from quant.stats import regress

FACTORS = {  # 列名：(中文名, 发表年份)
    "Mkt-RF": ("市场（股市减国债）", None),
    "SMB": ("规模（小公司减大公司）", 1981),
    "HML": ("价值（便宜减贵）", 1992),
    "Mom": ("动量（强势减弱势）", 1993),
}
LABEL_OFFSET = {"SMB": (-8, 10), "HML": (-8, -18), "Mom": (-8, 10)}  # 图上"发表"标注的位置，避开其他线
ETFS = {"SPY": "标普 500（大公司）", "IWM": "罗素 2000（小公司）", "QQQ": "纳斯达克 100（科技股为主）"}


def main():
    factors = load_factors()
    pd.set_option("display.unicode.east_asian_width", True)
    evidence(factors)
    checkup(factors)
    plot(factors)


def yearly(r):
    """(年均收益, t 值)：月均收益 × 12；t 值 = 月均 / (月标准差 / √月数)。"""
    return r.mean() * 12, r.mean() / (r.std() / np.sqrt(len(r)))


def evidence(factors):
    rows = {}
    for col, (name, year) in FACTORS.items():
        r = factors[col]
        full, t = yearly(r)
        row = {"全部 年均": full, "t 值": t}
        if year:
            before, t_before = yearly(r.loc[:f"{year}-12"])
            after, t_after = yearly(r.loc[f"{year + 1}-01":])
            row.update({"发表前 年均": before, "发表后 年均": after, "发表后 t 值": t_after})
        row["最近 20 年 年均"] = yearly(r.iloc[-240:])[0]
        rows[name] = row
    table = pd.DataFrame(rows).T
    pct, num = "{:+.1%}".format, "{:.1f}".format
    print(f"一、近百年的证据（{factors.index[0]} 至 {factors.index[-1]}，共 {len(factors)} 个月）\n")
    print(table.to_string(na_rep="—", formatters={
        "全部 年均": pct, "t 值": num, "发表前 年均": pct, "发表后 年均": pct,
        "发表后 t 值": num, "最近 20 年 年均": pct}))


def checkup(factors):
    rows = {}
    cols = list(FACTORS)
    for ticker, name in ETFS.items():
        monthly = to_monthly(load_prices(ticker)["Close"].pct_change().dropna()).iloc[1:]  # 去掉不完整的第一个月
        data = factors.join(monthly.rename("etf"), how="inner")
        res = regress(data["etf"] - data["RF"], data[cols])
        rows[f"{ticker} {name}"] = {
            "期间": f"{data.index[0]} 至 {data.index[-1]}",
            **{FACTORS[c][0][:2]: res["coef"][c] for c in cols},
            "年化 alpha": res["coef"]["alpha"] * 12, "alpha 的 t 值": res["t"]["alpha"], "R²": res["r2"],
        }
    table = pd.DataFrame(rows).T
    num2 = "{:+.2f}".format
    print("\n二、给基金做体检：对四个因子的暴露（系数），正数表示偏向这种因子\n")
    print(table.to_string(formatters={
        "市场": num2, "规模": num2, "价值": num2, "动量": num2,
        "年化 alpha": "{:+.1%}".format, "alpha 的 t 值": "{:.1f}".format, "R²": "{:.2f}".format}))


def plot(factors):
    use_style()
    fig, ax = plt.subplots(figsize=(10, 6))
    for (col, (name, year)), color in zip(FACTORS.items(), COLORS + ["#eda100"]):
        growth = (1 + factors[col]).cumprod()
        growth.index = growth.index.to_timestamp()
        ax.plot(growth, color=color, linewidth=1.5, label=name)
        label_line_end(ax, growth, f"{growth.iloc[-1]:,.0f} 美元", color)
        if year:  # 在发表那年年底标一个点
            when = pd.Timestamp(f"{year}-12-01")
            ax.plot(when, growth.loc[when], "o", ms=7, color=color, mec="white", mew=1.5, zorder=3)
            ax.annotate(f"发表 {year}", (when, growth.loc[when]), xytext=LABEL_OFFSET[col], textcoords="offset points",
                        ha="right", color=INK_SECONDARY, fontsize=9)
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:g}"))
    ax.set_ylabel("1 美元变成多少（对数刻度，不含国债利息）")
    ax.set_title("四个因子近百年的累计收益", loc="left")
    ax.legend(loc="upper left")
    print()
    save_figure(fig, "research_factors.png")


if __name__ == "__main__":
    main()

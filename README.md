# quant-bot

个人量化交易项目：用 Python 做回测，用 Alpaca 模拟账户自动交易。

A personal quantitative trading project: backtesting tools in Python and a scheduled bot that trades an Alpaca paper account.

> 仅供学习。程序只连接 Alpaca 的模拟盘（paper trading，用的是假钱），不涉及真实资金，也不构成任何投资建议。

## 策略

股票（SPY，标普 500）、美国国债（IEF，7–10 年期）、黄金（GLD）各占 1/3，每月调回目标比例（再平衡）。三样东西经常不一起涨跌，放在一起整体起伏更小。

- 留 1% 现金作缓冲，防止下单时价格变动导致钱不够
- 某一样偏离目标不到 100 美元就不调，省交易成本
- 买入按金额下单，卖出按股数下单（支持小数股）

## 结构

```
paper_rebalance.py    下单程序：演练 / 下单 / 定时自动运行
paper_status.py       查看账户：持仓、盈亏、订单（只读）
quant/
  alpaca.py             Alpaca 模拟账户客户端（地址写死成模拟盘）
  rebalance.py          算出调回目标比例要下哪些单
  risk.py               下单前的风控检查
  paths.py              密钥、日志、紧急停止开关放在哪
  notify.py             发 macOS 通知
  stats.py              统计工具：最小二乘回归（系数、标准误、t 值、R²）
  factors.py            Kenneth French 数据库的因子数据（1926 年至今，按月，没有幸存者偏差）
  data.py               回测工具：下载并缓存日线（Yahoo Finance）
  backtest.py           回测工具：向量化回测
  metrics.py            回测工具：年化收益、波动、夏普、最大回撤
  portfolio.py          回测工具：多资产组合，定期再平衡
  plot.py               回测工具：统一的画图样式
scheduler/
  install.sh            部署到 ~/quant-bot，并注册每天运行的定时任务（macOS launchd）
  uninstall.sh          撤掉定时任务
research/             策略研究，每个问题一个脚本（在项目根目录用 python -m research.脚本名 运行）
```

## 设计

- **只连模拟盘**：API 地址写死成 `paper-api.alpaca.markets`，程序碰不到真钱账户
- **默认只演练**：不加参数时只打印打算下的单；加 `--submit` 才下单
- **下单前风控**，任何一条不通过都不下单：
  - 单笔不超过账户总值的 40%，一次买卖总额不超过账户总值
  - 只交易 SPY、IEF、GLD
  - 每月最多交易一次（确实要再交易加 `--force`）
  - 还有没成交的单子时不下新单，避免重复
  - 紧急停止开关：存在 `~/quant-bot/STOP` 文件就一律不下单
- **开发和生产分开**：这个仓库是开发环境；`install.sh` 把下单程序部署到 `~/quant-bot`，定时任务从那里运行。改代码、做实验不会影响正在跑的程序。另一个原因是 macOS 不让后台程序读「文稿」文件夹
- **全部留记录**：每笔单子、每次月度检查的结果都写进日志
- **出事会通知**：调仓完成、月度检查不用交易、被风控拦下、有单子一直没成交、程序出错时，弹 macOS 通知。平时每天的"本月已检查"不通知

## 使用

需要 macOS 和 Python 3.9+。

1. 装依赖：

   ```bash
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   ```

2. 在 [Alpaca](https://app.alpaca.markets/signup) 注册模拟账户（只要邮箱），生成 Paper 的 API 密钥。把 `.env.example` 复制成 `.env`，填上密钥。**不要把 `.env` 提交到 git**，`.gitignore` 已经排除了它

3. 手动运行：

   ```bash
   .venv/bin/python paper_rebalance.py            # 演练，只打印打算下的单
   .venv/bin/python paper_rebalance.py --submit   # 下单到模拟账户
   .venv/bin/python paper_status.py               # 查看账户
   ```

4. 定时运行：

   ```bash
   bash scheduler/install.sh           # 部署到 ~/quant-bot、注册，并马上试跑一次
   bash scheduler/install.sh --print   # 只看要注册的定时任务，不做任何改动
   bash scheduler/uninstall.sh         # 撤掉定时任务
   ```

   每天 15:00（本机时间）运行 `paper_rebalance.py --auto`：这个月检查过就直接退出，没检查过就检查并在需要时调仓。到点时电脑在睡眠，醒来后会补跑；关机则跳过那一次，第二天再跑。第一次运行 `install.sh` 会把 `.env` 挪到 `~/quant-bot/`。

   **改了下单相关的代码之后，要重新运行一次 `install.sh`，新代码才会部署过去。**

### 文件位置

| 东西 | 位置 |
|---|---|
| 模拟账户密钥 | `~/quant-bot/.env` |
| 下单记录 | `~/quant-bot/logs/paper_orders.csv` |
| 每月检查的结果 | `~/quant-bot/logs/paper_runs.csv` |
| 紧急停止开关 | `~/quant-bot/STOP`：`touch ~/quant-bot/STOP` 暂停，`rm ~/quant-bot/STOP` 恢复 |
| 定时任务的运行输出 | `~/Library/Logs/quant-paper-rebalance.log` |

## 回测工具

研究新策略时，先回测，再决定要不要部署。比如"价格在 200 日均线之上就持有"：

```python
from quant.data import load_prices
from quant.backtest import run_backtest
from quant.metrics import summary

close = load_prices("SPY")["Close"]
signal = (close > close.rolling(200).mean()).astype(float)
print(summary(run_backtest(close, signal)["strategy"]))
```

回测按收盘时的信号在下一天持仓，避免用到未来的数据；默认每次买卖扣 0.05% 的成本。

## 研究记录

每项研究都在看结果之前定好判断标准，参数不调。

| 研究 | 问题 | 结论 |
|---|---|---|
| `research/trend_filter.py` | 各 1/3 组合加 200 日均线趋势过滤（跌破均线的那 1/3 换成现金）会不会更好？标准：2016 年前后两段都夏普更高、最大回撤更小 | **没通过**。2016 年前明显更好（夏普 0.96 对 0.69），2016 年后更差（0.64 对 0.88）；两段的最大回撤都更小。机器人保持原策略 |
| `research/survivorship.py` | 用今天市值最大的 10 家公司回测 2013 年以来，会得到什么？（演示幸存者偏差，不是可用的策略） | 年化 36%、夏普 1.36，1 美元变成 68 美元；同期 SPY 年化 15%，变成 7 美元。好得不真实：这些公司正是因为涨得最好才成了今天最大的。**以后做选股研究，必须用当时的成分股，并包括后来退市的公司** |
| `research/capm.py` | 把收益拆成"跟着大盘的部分"（beta）和"自己的部分"（alpha），alpha 是不是运气？ | A 的 beta 0.36、年化 alpha 3.6%（t 值 2.4），但把国债、黄金也放进回归后 alpha 完全消失：它只是其他资产的收益，不是本事。事后挑的前 10 大 alpha 16%、t 值 4.9，非常"显著"，却是假的。**alpha 取决于拿什么比；统计检验只能排除运气，排除不了研究设计本身的错误** |
| `research/factors.py` | 规模、价值、动量这几个学术界公认的因子，近百年（1927–2026）真的有效吗？公开发表之后还有效吗？ | 市场因子最稳（年均 8.3%，t 值 4.5）。三个因子发表后都大幅变弱：规模 3.6% → 0.2%，价值 5.3% → 2.2%，动量 8.8% → 4.3%，发表后的 t 值都不到 2；最近 20 年价值因子是负的。用因子给基金做体检，结果和直觉一致：IWM 偏小公司（+0.82），QQQ 明显偏"贵"的成长股（价值 −0.67）。**规律一旦公开就会被交易掉一部分，发表后的表现才是真正的样本外** |

## 计划

- 通知发到手机，不在电脑前也能收到
- 研究新策略，回测过关后再部署

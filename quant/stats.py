"""统计工具：最小二乘回归，用来把收益拆成"跟着大盘的部分"和"自己的部分"。"""

import numpy as np
import pandas as pd


def regress(y: pd.Series, X: pd.DataFrame) -> dict:
    """最小二乘回归 y = alpha + X·beta + 误差。

    返回每个系数的估计值、标准误、t 值，以及 R²（y 的波动有多少能被 X 解释）。
    t 值的绝对值大于 2，大致表示有 95% 的把握这个系数不是 0，不是运气。
    """
    data = pd.concat([y, X], axis=1).dropna()
    target = data.iloc[:, 0].to_numpy()
    design = np.column_stack([np.ones(len(data)), data.iloc[:, 1:].to_numpy()])
    # numpy 2.0 在 macOS 上做矩阵乘法会误报 divide by zero / overflow 警告（已知问题），结果不受影响
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        coef, *_ = np.linalg.lstsq(design, target, rcond=None)
        resid = target - design @ coef
        n, k = design.shape
        sigma2 = resid @ resid / (n - k)                                   # 误差的方差
        stderr = np.sqrt(np.diag(sigma2 * np.linalg.inv(design.T @ design)))
        centered = target - target.mean()
        r2 = 1 - resid @ resid / (centered @ centered)
        t = coef / stderr
    if 1 - r2 < 1e-12:  # 完全拟合：误差只剩浮点舍入，t 值没有意义
        t = np.full_like(coef, np.nan)
    names = ["alpha"] + list(X.columns)
    return {
        "coef": pd.Series(coef, index=names),
        "stderr": pd.Series(stderr, index=names),
        "t": pd.Series(t, index=names),
        "r2": r2,
        "n": n,
    }

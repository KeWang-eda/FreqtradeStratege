"""momentum_engine: 策略共享的动量计算引擎.

从 SevenStarCrypto / FiveBlessCrypto 提取的公共计算模块(消除跨策略重复):
  - weighted_log_regression: 加权log回归年化 x R2 滚动打分(FFT 卷积加速)
  - laplace_filter: 拉普拉斯滤波(EWM等价)
  - volume_ratio: 量比(当前量/前N根均量, 不含当前)
  - recent_drop_mask: 近N根单根跌幅超阈值掩码

注意: 所有函数均为向量化逐行计算(防未来函数), 由调用方负责 shift.
"""
import numpy as np
from pandas import Series


def fftconvolve(a: np.ndarray, v: np.ndarray) -> np.ndarray:
    """FFT 卷积(与 np.convolve 'full' 语义一致, O(m log m))."""
    out_len = len(a) + len(v) - 1
    nf = 1 << (out_len - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(a, nf) * np.fft.rfft(v, nf))[:out_len]


def weighted_log_regression(closes: Series, n: int,
                            weight_power: float = 1.0,
                            annualize_bars: int = 250,
                            score_mode: str = "exp"
                            ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """滚动加权log回归: 年化收益 x R2. 返回 (score, annualized, slope).

    Args:
        closes: 价格序列.
        n: 回归窗口长度(K线数).
        weight_power: 权重幂次. 1.0=单重(SevenStar), 2.0=双重(FiveBless).
        annualize_bars: 年化K线数. 250=A股交易日(源口径, 默认不变);
            币市 7x24 的 N 分钟策略传 365*24*60/N (5min -> 105120).
        score_mode: 得分变换. ``exp`` 保留历史的 ``exp(log_return)-1``;
            ``signed_log`` 使用带符号的年化log收益, 让正负分数严格对称.

    Returns:
        score: 年化 x R2 数组(与输入等长, 前n根为0).
        annualized: 年化收益数组.
        slope: 拟合斜率数组.

    实现: WLS 闭式解 + 卷积加速. 窗口权重绑定"窗口内位置"
    (x=arange(n+1), 最新bar权重最大), 窗口滑动时各元素权重随之平移,
    不能用 O(1) 增减维护; 但 ΣW·f(y) 是固定卷积核的滑动内积,
    用 FFT 卷积 O(m log m) 一次算出全部窗口的累积量(与逐窗口
    循环计算数值等价, 浮点级差异). 窗口含 NaN 时该位置输出 0
    (与历史语义一致).
    """
    log_close = np.log(closes.replace(0, np.nan))
    arr = log_close.to_numpy(dtype=float)
    m = len(arr)
    score = np.zeros(m)
    annualized = np.zeros(m)
    slope_out = np.zeros(m)   # 新增，用于返回斜率
    win_len = n + 1
    if m <= win_len:
        return score, annualized, slope_out
    x = np.arange(win_len, dtype=float)
    w = np.linspace(1.0, 2.0, win_len)
    W = w ** weight_power
    S_w = float(W.sum())
    S_wx = float((W * x).sum())
    S_wxx = float((W * x * x).sum())
    denom = S_wxx - S_wx * S_wx / S_w  # ΣW(x-x̄)²
    if np.isclose(denom, 0.0):
        return score, annualized, slope_out
    # 卷积核(反转后, 使 conv[i] = Σ_k W[k]·arr[i-n+k], 窗口尾部对齐输出位置 i)
    # NaN 会经 FFT 全局污染输出, 先填 0 再卷积, 用窗口 NaN 计数掩码排除
    nan_flag = np.isnan(arr)
    arr_fill = np.where(nan_flag, 0.0, arr)
    Wr = W[::-1]
    Wxr = (W * x)[::-1]
    S_wy_arr = fftconvolve(arr_fill, Wr)[:m]
    S_wxy_arr = fftconvolve(arr_fill, Wxr)[:m]
    S_wyy_arr = fftconvolve(arr_fill * arr_fill, Wr)[:m]
    # R² 用基础权重 w(既定行为: 斜率 W=w^weight_power, ss_res/ss_tot 用 w;
    # wp=1.0 时 w==W 可复用, wp=2.0 需单独卷积)
    if weight_power == 1.0:
        T_wy_arr, T_wxy_arr, T_wyy_arr = S_wy_arr, S_wxy_arr, S_wyy_arr
        S_w_base, Swx_base, Swxx_base = S_w, S_wx, S_wxx
    else:
        wr = w[::-1]
        T_wy_arr = fftconvolve(arr_fill, wr)[:m]
        T_wxy_arr = fftconvolve(arr_fill, (w * x)[::-1])[:m]
        T_wyy_arr = fftconvolve(arr_fill * arr_fill, wr)[:m]
        S_w_base = float(w.sum())
        Swx_base = float((w * x).sum())
        Swxx_base = float((w * x * x).sum())
    nan_in_window = (np.convolve(nan_flag.astype(int),
                                 np.ones(win_len, dtype=int), 'full')[:m] > 0)
    # 只取有效输出位置 i >= win_len(窗口满 win_len 根), 且窗口内无 NaN
    y_bar = S_wy_arr / S_w
    slope = (S_wxy_arr - S_wx * y_bar) / denom
    intercept = y_bar - slope * (S_wx / S_w)
    ss_tot = (T_wyy_arr - 2 * y_bar * T_wy_arr
              + y_bar * y_bar * S_w_base)
    ss_pos = ss_tot > 0
    ss_res = (T_wyy_arr - 2 * slope * T_wxy_arr - 2 * intercept * T_wy_arr
              + slope * slope * Swxx_base
              + 2 * slope * intercept * Swx_base
              + intercept * intercept * S_w_base)
    r2v = np.where(ss_pos, 1.0 - ss_res / np.where(ss_pos, ss_tot, 1.0), 0.0)
    ok = (np.arange(m) >= win_len) & ~nan_in_window
    with np.errstate(over='ignore', invalid='ignore'):
        ann = np.exp(slope * annualize_bars) - 1.0
    annualized = np.where(ok, ann, 0.0)
    slope_out = np.where(ok, slope, 0.0)   # 斜率，带符号
    # ``exp`` 是基线口径；``signed_log`` 避免正收益指数爆炸、负收益饱和，
    # 直接在 log-return 空间保留方向和幅度的镜像关系。
    if score_mode == "exp":
        score_value = ann
    elif score_mode == "signed_log":
        score_value = slope * annualize_bars
    else:
        raise ValueError(f"unsupported score_mode: {score_mode}")
    score = np.where(ok, score_value * r2v, 0.0)
    return score, annualized, slope_out

def laplace_filter(series: Series, s: float = 0.05) -> Series:
    """拉普拉斯滤波(EWM等价, 向量化)."""
    alpha = 1 - np.exp(-s)
    return series.ewm(alpha=alpha, adjust=False).mean()


def volume_ratio(volumes: Series, lookback: int) -> Series:
    """量比: 当前量 / 前 lookback 根均量(不含当前)."""
    avg_vol_prev = volumes.rolling(lookback,
                                   min_periods=1).mean().shift(1)
    return volumes / avg_vol_prev.replace(0, np.nan)


def recent_drop_mask(closes: Series, threshold: float,
                     n: int = 3) -> Series:
    """近N根单根跌幅超阈值掩码(向量化)."""
    mask = closes / closes.shift(1) < threshold
    for i in range(1, n):
        mask = mask | (closes.shift(i) / closes.shift(i + 1) < threshold)
    return mask.fillna(False)

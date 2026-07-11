"""
加密貨幣多幣種驗證 + ATR 動態停損
------------------------------------
沿用股票測試的同一套邏輯（20/60均線 + ATR浮動停損），
套用到 BTC / ETH / SOL 三個主流幣，理由：
  - 加密貨幣 24 小時交易，沒有「隔夜跳空」的財報崩盤風險（但仍有其他黑天鵝）
  - 但也絕不能只測 BTC 一個標的，否則又會掉進單一標的巧合的陷阱

執行方式：
    python crypto_atr_backtest.py
"""

import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "SimHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False

# ---------- 參數設定 ----------
TICKERS = ["BTC-USD", "ETH-USD", "LTC-USD", "BCH-USD", "XRP-USD", "BNB-USD", "ADA-USD", "LINK-USD", "SOL-USD"]
TICKER_START_OVERRIDES = {
    "SOL-USD": "2021-01-01",  # SOL 2020年還是幾毛錢，從2021年幣價進入合理量級後才開始測，避開基期效應
}
START_DATE = "2018-01-01"   # SOL 資料較晚才有，程式會自動從有資料的日期開始算
END_DATE = "2025-01-01"
SHORT_WINDOW = 20
LONG_WINDOW = 60
ATR_WINDOW = 14
ATR_MULTIPLIER = 3.0
INITIAL_CAPITAL = 10000
RISK_PER_TRADE_PCT = 0.02   # 每筆交易最多承擔帳戶 2% 的風險（用停損距離反推部位大小）


def fetch_data(ticker, start, end):
    df = yf.download(ticker, start=start, end=end, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["High", "Low", "Close"]].dropna()
    return df


def generate_signals(df):
    df = df.copy()
    df["MA_short"] = df["Close"].rolling(SHORT_WINDOW).mean()
    df["MA_long"] = df["Close"].rolling(LONG_WINDOW).mean()
    df["signal"] = 0
    df.loc[df["MA_short"] > df["MA_long"], "signal"] = 1

    prev_close = df["Close"].shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_close).abs(),
        (df["Low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(ATR_WINDOW).mean()
    return df


def backtest(df, initial_capital, use_atr_stop, use_position_sizing=False):
    capital = initial_capital
    in_position = False
    entry_price = entry_capital = highest_since_entry = cash_reserve = None
    equity_list = []
    num_trades = num_stop_exits = 0

    for _, row in df.iterrows():
        price = row["Close"]
        if not in_position:
            equity_list.append(capital)
            if row["signal"] == 1:
                in_position = True
                entry_price = price
                highest_since_entry = price

                if use_position_sizing and pd.notna(row["ATR"]):
                    stop_distance_pct = (ATR_MULTIPLIER * row["ATR"]) / price
                    position_fraction = min(1.0, RISK_PER_TRADE_PCT / stop_distance_pct) if stop_distance_pct > 0 else 1.0
                else:
                    position_fraction = 1.0  # 沒開部位控制，或ATR還沒算出來，就用全部資金

                entry_capital = capital * position_fraction
                cash_reserve = capital - entry_capital
        else:
            highest_since_entry = max(highest_since_entry, price)
            atr = row["ATR"]
            has_atr = use_atr_stop and pd.notna(atr)
            stop_price = highest_since_entry - ATR_MULTIPLIER * atr if has_atr else -np.inf
            stop_triggered = has_atr and price <= stop_price
            ma_exit = row["signal"] == 0

            if stop_triggered or ma_exit:
                current_return = price / entry_price - 1
                capital = cash_reserve + entry_capital * (1 + current_return)
                num_trades += 1
                if stop_triggered:
                    num_stop_exits += 1
                in_position = False
                equity_list.append(capital)
            else:
                equity_list.append(cash_reserve + entry_capital * (price / entry_price))

    equity_curve = pd.Series(equity_list, index=df.index)
    total_return = equity_curve.iloc[-1] / initial_capital - 1
    running_max = equity_curve.cummax()
    max_drawdown = ((equity_curve - running_max) / running_max).min()

    return equity_curve, {
        "total_return": total_return,
        "max_drawdown": max_drawdown,
        "num_trades": num_trades,
        "num_stop_exits": num_stop_exits,
    }


def run_all():
    results = []
    curves = {}
    for ticker in TICKERS:
        try:
            start = TICKER_START_OVERRIDES.get(ticker, START_DATE)
            df = fetch_data(ticker, start, END_DATE)
            df = generate_signals(df)
        except Exception as e:
            print(f"{ticker} 抓取失敗，略過（原因: {e}）")
            continue

        years = (df.index[-1] - df.index[0]).days / 365.25
        buy_hold_return = df["Close"].iloc[-1] / df["Close"].iloc[0] - 1
        _, no_stop = backtest(df, INITIAL_CAPITAL, use_atr_stop=False)
        curve_atr, atr_stop = backtest(df, INITIAL_CAPITAL, use_atr_stop=True)
        curve_sized, sized = backtest(df, INITIAL_CAPITAL, use_atr_stop=True, use_position_sizing=True)
        curves[ticker] = (df, curve_atr, buy_hold_return)

        results.append({
            "ticker": ticker,
            "years": years,
            "buy_hold": buy_hold_return,
            "no_stop_return": no_stop["total_return"],
            "atr_return": atr_stop["total_return"],
            "atr_dd": atr_stop["max_drawdown"],
            "sized_return": sized["total_return"],
            "sized_dd": sized["max_drawdown"],
            "atr_trades": atr_stop["num_trades"],
            "atr_stops": atr_stop["num_stop_exits"],
            "beats_bh": atr_stop["total_return"] > buy_hold_return,
        })
    return pd.DataFrame(results), curves


def print_report(df):
    print("=" * 120)
    print(f"{'幣種':<10}{'資料年數':>8}{'買進持有':>10}{'ATR停損':>10}{'ATR回撤':>10}{'部位控制':>10}{'控制後回撤':>10}{'贏大盤?':>8}")
    print("=" * 120)
    for _, r in df.iterrows():
        print(f"{r['ticker']:<10}{r['years']:>7.1f}年{r['buy_hold']:>10.2%}"
              f"{r['atr_return']:>10.2%}{r['atr_dd']:>10.2%}"
              f"{r['sized_return']:>10.2%}{r['sized_dd']:>10.2%}"
              f"{'是' if r['beats_bh'] else '否':>8}")
    print("=" * 120)
    avg_dd_before = df["atr_dd"].mean()
    avg_dd_after = df["sized_dd"].mean()
    print(f"\n平均最大回撤（無部位控制）: {avg_dd_before:.2%}")
    print(f"平均最大回撤（有部位控制）: {avg_dd_after:.2%}")
    print(f"回撤改善幅度: {avg_dd_after - avg_dd_before:.2%}")


def plot_curves(curves):
    fig, axes = plt.subplots(1, len(curves), figsize=(6 * len(curves), 5))
    if len(curves) == 1:
        axes = [axes]
    for ax, (ticker, (df, curve_atr, bh_return)) in zip(axes, curves.items()):
        bh_curve = (df["Close"] / df["Close"].iloc[0]) * INITIAL_CAPITAL
        ax.plot(curve_atr.index, curve_atr, label="策略(ATR停損)")
        ax.plot(bh_curve.index, bh_curve, label="買進持有", alpha=0.7)
        ax.set_title(ticker)
        ax.legend()
    plt.tight_layout()
    plt.savefig("crypto_equity_curves.png", dpi=150)
    print("圖表已儲存為 crypto_equity_curves.png")


if __name__ == "__main__":
    results_df, curves = run_all()
    print_report(results_df)
    plot_curves(curves)

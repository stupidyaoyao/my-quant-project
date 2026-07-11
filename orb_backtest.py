"""
ORB（開盤區間突破）參數優化：2R vs 1.5R
------------------------------------------------
只針對第一階段擴大樣本後表現最好的兩個候選組合，比較不同停利倍數：
  - 30分鐘 回測確認型
  - 15分鐘 標準型
刻意不對其他組合做這個優化，避免多重比較稀釋信度、重蹈過度優化覆轍。

執行方式：
    python orb_backtest.py
"""

import pandas as pd
import numpy as np
import yfinance as yf

# ---------- 參數設定 ----------
TICKERS = ["QQQ", "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META",
           "INTC", "XOM", "JNJ", "KO", "PYPL", "DIS", "BA"]

# 只測這兩組候選，窗口名稱換算成5分鐘K棒根數
CANDIDATES = [
    ("30分鐘", 6, "回測確認型"),
    ("15分鐘", 3, "標準型"),
]
TAKE_PROFIT_R_OPTIONS = [1.5, 2.0]

RETEST_TOLERANCE_PCT = 0.003
MIN_RISK_PCT = 0.001
RISK_PER_TRADE_PCT = 0.02
INITIAL_CAPITAL = 10000


def fetch_intraday(ticker):
    df = yf.download(ticker, period="60d", interval="5m", auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close"]].dropna()
    return df


def simulate_exit(bars_after, entry_price, stop_price, target_price, direction, take_profit_r):
    for _, row in bars_after.iterrows():
        if direction == "long":
            if row["Low"] <= stop_price:
                return -1.0
            if row["High"] >= target_price:
                return take_profit_r
        else:
            if row["High"] >= stop_price:
                return -1.0
            if row["Low"] <= target_price:
                return take_profit_r
    if bars_after.empty:
        return 0.0
    last_close = bars_after["Close"].iloc[-1]
    risk = abs(entry_price - stop_price)
    if risk == 0:
        return 0.0
    if direction == "long":
        return (last_close - entry_price) / risk
    else:
        return (entry_price - last_close) / risk


def simulate_day(df_day, k, variant, direction, take_profit_r):
    if len(df_day) < k + 2:
        return None
    or_high = df_day["High"].iloc[:k].max()
    or_low = df_day["Low"].iloc[:k].min()
    remaining = df_day.iloc[k:]

    if direction == "long":
        breakout_mask = remaining["Close"] > or_high
        level = or_high
    else:
        breakout_mask = remaining["Close"] < or_low
        level = or_low

    breakout_candidates = remaining[breakout_mask]
    if breakout_candidates.empty:
        return None
    breakout_idx = breakout_candidates.index[0]

    if variant == "標準型":
        entry_price = remaining.loc[breakout_idx, "Close"]
        stop_price = remaining.loc[breakout_idx, "Low"] if direction == "long" else remaining.loc[breakout_idx, "High"]
        after = remaining.loc[breakout_idx:].iloc[1:]
    else:
        after_breakout = remaining.loc[breakout_idx:].iloc[1:]
        tolerance = level * RETEST_TOLERANCE_PCT
        if direction == "long":
            retest_mask = (after_breakout["Low"] <= level + tolerance) & (after_breakout["Close"] > level)
        else:
            retest_mask = (after_breakout["High"] >= level - tolerance) & (after_breakout["Close"] < level)
        retest_candidates = after_breakout[retest_mask]
        if retest_candidates.empty:
            return None
        confirm_idx = retest_candidates.index[0]
        entry_price = remaining.loc[confirm_idx, "Close"]
        stop_price = remaining.loc[confirm_idx, "Low"] if direction == "long" else remaining.loc[confirm_idx, "High"]
        after = remaining.loc[confirm_idx:].iloc[1:]

    risk = abs(entry_price - stop_price)
    if risk == 0 or (risk / entry_price) < MIN_RISK_PCT:
        return None
    target_price = entry_price + take_profit_r * risk if direction == "long" else entry_price - take_profit_r * risk
    return simulate_exit(after, entry_price, stop_price, target_price, direction, take_profit_r)


def run_backtest():
    all_trades = []

    for ticker in TICKERS:
        print(f"抓取 {ticker} 分鐘資料中...")
        try:
            data = fetch_intraday(ticker)
        except Exception as e:
            print(f"⚠️ {ticker} 抓取失敗，略過（原因: {e}）")
            continue

        for date, df_day in data.groupby(data.index.date):
            for window_name, k, variant in CANDIDATES:
                for take_profit_r in TAKE_PROFIT_R_OPTIONS:
                    for direction in ["long", "short"]:
                        r = simulate_day(df_day, k, variant, direction, take_profit_r)
                        if r is not None:
                            all_trades.append({
                                "ticker": ticker, "date": date, "window": window_name,
                                "variant": variant, "take_profit_r": take_profit_r,
                                "direction": direction, "R": r,
                            })

    return pd.DataFrame(all_trades)


def print_report(trades_df):
    if trades_df.empty:
        print("沒有產生任何交易紀錄")
        return

    print("\n" + "=" * 110)
    print(f"{'候選組合':<20}{'停利倍數':>8}{'交易次數':>8}{'勝率':>8}{'平均R':>8}{'總R':>8}{'模擬報酬率':>12}{'集中度':>8}")
    print("=" * 110)

    for window_name, k, variant in CANDIDATES:
        for take_profit_r in TAKE_PROFIT_R_OPTIONS:
            subset = trades_df[(trades_df["window"] == window_name) & (trades_df["variant"] == variant)
                                & (trades_df["take_profit_r"] == take_profit_r)]
            label = f"{window_name}{variant}"
            if subset.empty:
                print(f"{label:<20}{take_profit_r:>8.1f}{'0':>8}{'-':>8}{'-':>8}{'-':>8}{'-':>12}{'-':>8}")
                continue

            subset_sorted = subset.sort_values("date")
            win_rate = (subset_sorted["R"] > 0).mean()
            avg_r = subset_sorted["R"].mean()
            total_r = subset_sorted["R"].sum()
            max_r = subset_sorted["R"].max()
            concentration = max_r / total_r if total_r > 0 else float("nan")

            equity = INITIAL_CAPITAL
            for r in subset_sorted["R"]:
                equity *= (1 + r * RISK_PER_TRADE_PCT)
            sim_return = equity / INITIAL_CAPITAL - 1

            print(f"{label:<20}{take_profit_r:>8.1f}{len(subset):>8}{win_rate:>8.1%}"
                  f"{avg_r:>8.2f}{total_r:>8.1f}{sim_return:>12.2%}{concentration:>8.1%}")

    print("=" * 110)
    print(f"\n（樣本期間：最近約60個交易日；模擬報酬率假設每筆交易風險帳戶資金 {RISK_PER_TRADE_PCT:.0%}）")


if __name__ == "__main__":
    trades = run_backtest()
    print_report(trades)

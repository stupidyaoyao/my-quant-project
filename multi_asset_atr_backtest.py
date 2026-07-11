"""
多商品驗證 + ATR 動態停損
----------------------------
1. 用同一組固定參數（20/60 均線 + ATR 浮動停損），測試多支不同產業的股票和 QQQ
2. 目的：驗證這組策略邏輯是否有「普遍性」的優勢，而不是只在單一股票的特定歷史片段有效
3. ATR 停損原理：停損點跟著股價創新高往上移動（Chandelier Stop），
   跌破「近期最高價 - N倍ATR」就出場，停損寬度會隨波動性自動放大或收窄

執行方式：
    python multi_asset_atr_backtest.py
"""

import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "SimHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False

# ---------- 參數設定 ----------
TICKERS = ["QQQ", "AAPL", "MSFT", "XOM", "JNJ", "KO", "PYPL", "DIS", "BA", "INTC"]
START_DATE = "2020-01-01"
END_DATE = "2025-01-01"
SHORT_WINDOW = 20
LONG_WINDOW = 60
ATR_WINDOW = 14
ATR_MULTIPLIER = 3.0     # 停損距離 = N 倍 ATR，數字越大停損越寬鬆
INITIAL_CAPITAL = 10000


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


def backtest(df, initial_capital, use_atr_stop):
    capital = initial_capital
    in_position = False
    entry_price = entry_capital = highest_since_entry = None
    equity_list = []
    num_trades = num_stop_exits = 0

    for _, row in df.iterrows():
        price = row["Close"]
        if not in_position:
            equity_list.append(capital)
            if row["signal"] == 1:
                in_position = True
                entry_price, entry_capital = price, capital
                highest_since_entry = price
        else:
            highest_since_entry = max(highest_since_entry, price)
            atr = row["ATR"]
            has_atr = use_atr_stop and pd.notna(atr)
            stop_price = highest_since_entry - ATR_MULTIPLIER * atr if has_atr else -np.inf
            stop_triggered = has_atr and price <= stop_price
            ma_exit = row["signal"] == 0

            if stop_triggered or ma_exit:
                current_return = price / entry_price - 1
                capital = entry_capital * (1 + current_return)
                num_trades += 1
                if stop_triggered:
                    num_stop_exits += 1
                in_position = False
                equity_list.append(capital)
            else:
                equity_list.append(entry_capital * (price / entry_price))

    equity_curve = pd.Series(equity_list, index=df.index)
    total_return = equity_curve.iloc[-1] / initial_capital - 1
    running_max = equity_curve.cummax()
    max_drawdown = ((equity_curve - running_max) / running_max).min()

    return {
        "total_return": total_return,
        "max_drawdown": max_drawdown,
        "num_trades": num_trades,
        "num_stop_exits": num_stop_exits,
    }


def run_all():
    results = []
    for ticker in TICKERS:
        try:
            df = fetch_data(ticker, START_DATE, END_DATE)
            df = generate_signals(df)
        except Exception as e:
            print(f"{ticker} 抓取失敗，略過（原因: {e}）")
            continue

        buy_hold_return = df["Close"].iloc[-1] / df["Close"].iloc[0] - 1
        no_stop = backtest(df, INITIAL_CAPITAL, use_atr_stop=False)
        atr_stop = backtest(df, INITIAL_CAPITAL, use_atr_stop=True)

        results.append({
            "ticker": ticker,
            "buy_hold": buy_hold_return,
            "no_stop_return": no_stop["total_return"],
            "no_stop_dd": no_stop["max_drawdown"],
            "atr_return": atr_stop["total_return"],
            "atr_dd": atr_stop["max_drawdown"],
            "atr_trades": atr_stop["num_trades"],
            "atr_stops": atr_stop["num_stop_exits"],
            "beats_bh": atr_stop["total_return"] > buy_hold_return,
        })
    return pd.DataFrame(results)


def print_report(df):
    print("=" * 100)
    print(f"{'股票':<6}{'買進持有':>10}{'無停損':>10}{'ATR停損':>10}{'ATR回撤':>10}{'交易次數':>8}{'ATR出場':>8}{'贏大盤?':>8}")
    print("=" * 100)
    for _, r in df.iterrows():
        print(f"{r['ticker']:<6}{r['buy_hold']:>10.2%}{r['no_stop_return']:>10.2%}"
              f"{r['atr_return']:>10.2%}{r['atr_dd']:>10.2%}{r['atr_trades']:>8}"
              f"{r['atr_stops']:>8}{'是' if r['beats_bh'] else '否':>8}")
    print("=" * 100)

    win_rate = df["beats_bh"].mean()
    avg_excess = (df["atr_return"] - df["buy_hold"]).mean()
    print(f"\n策略贏過買進持有的商品比例: {win_rate:.0%}（{df['beats_bh'].sum()} / {len(df)}）")
    print(f"平均超額報酬（策略 - 買進持有）: {avg_excess:.2%}")
    print(f"平均 ATR 停損觸發次數: {df['atr_stops'].mean():.1f} 次")


if __name__ == "__main__":
    results_df = run_all()
    print_report(results_df)

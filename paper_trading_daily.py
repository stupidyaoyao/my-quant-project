"""
每日模擬交易訊號檢查（多商品版）
------------------------------------
每天執行一次，同時檢查多個商品的訊號：
  1. 抓最新資料，判斷每個商品該「買進」「續抱」「賣出」還是「觀望」
  2. 把每個商品的持倉狀態分別記住（存在同一個JSON裡，用商品名稱區分）
  3. 記錄到 paper_trading_log.csv，之後可以用網頁儀表板查看

⚠️ 只給建議，不會真的幫你下單。

執行方式（建議每天收盤後跑一次）：
    python paper_trading_daily.py
"""

import json
import os
import csv
from datetime import datetime

import pandas as pd
import numpy as np
import yfinance as yf

# ---------- 參數設定 ----------
TICKERS = ["BTC-USD", "ETH-USD", "QQQ"]   # 想追蹤的商品清單，可以自由增減
SHORT_WINDOW = 20
LONG_WINDOW = 60
ATR_WINDOW = 14
ATR_MULTIPLIER = 3.0
RISK_PER_TRADE_PCT = 0.02

STATE_FILE = "paper_trading_state.json"
LOG_FILE = "paper_trading_log.csv"


def fetch_recent_data(ticker):
    df = yf.download(ticker, period="400d", auto_adjust=True, progress=False)
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


def load_all_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_all_state(all_state):
    with open(STATE_FILE, "w") as f:
        json.dump(all_state, f, indent=2)


def log_result(date, ticker, price, recommendation, in_position):
    file_exists = os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["日期", "商品", "收盤價", "持倉狀態", "建議"])
        writer.writerow([date, ticker, f"{price:.2f}", "持倉中" if in_position else "空手", recommendation])


def check_ticker(ticker, state):
    df = fetch_recent_data(ticker)
    df = generate_signals(df)
    latest = df.iloc[-1]
    price = latest["Close"]
    atr = latest["ATR"]
    today = df.index[-1].date()

    if not state.get("in_position", False):
        if latest["signal"] == 1:
            if pd.notna(atr):
                stop_distance_pct = (ATR_MULTIPLIER * atr) / price
                position_fraction = min(1.0, RISK_PER_TRADE_PCT / stop_distance_pct) if stop_distance_pct > 0 else 1.0
            else:
                position_fraction = 1.0
            recommendation = f"買進訊號！建議投入資金比例約 {position_fraction:.0%}"
            state = {
                "in_position": True,
                "entry_price": price,
                "entry_date": str(today),
                "highest_since_entry": price,
                "position_fraction": position_fraction,
            }
        else:
            recommendation = "空手觀望，尚未出現買進訊號"
    else:
        entry_price = state["entry_price"]
        highest = max(state["highest_since_entry"], price)
        stop_price = highest - ATR_MULTIPLIER * atr if pd.notna(atr) else -np.inf
        stop_triggered = pd.notna(atr) and price <= stop_price
        ma_exit = latest["signal"] == 0
        current_return = price / entry_price - 1

        if stop_triggered or ma_exit:
            reason = "ATR停損" if stop_triggered else "均線死亡交叉"
            recommendation = f"賣出訊號！原因：{reason}，這筆交易報酬約 {current_return:.2%}"
            state = {"in_position": False}
        else:
            recommendation = f"續抱。浮動損益 {current_return:.2%}，目前停損價位約 ${stop_price:.2f}"
            state["highest_since_entry"] = highest

    return today, price, recommendation, state


def main():
    all_state = load_all_state()

    print(f"===== 每日訊號檢查 — {datetime.now().strftime('%Y-%m-%d')} =====\n")
    for ticker in TICKERS:
        ticker_state = all_state.get(ticker, {"in_position": False})
        today, price, recommendation, new_state = check_ticker(ticker, ticker_state)
        all_state[ticker] = new_state

        print(f"【{ticker}】 收盤價: ${price:,.2f}")
        print(f"  判斷: {recommendation}\n")

        log_result(today, ticker, price, recommendation, new_state.get("in_position", False))

    save_all_state(all_state)
    print(f"已記錄到 {LOG_FILE}")


if __name__ == "__main__":
    main()

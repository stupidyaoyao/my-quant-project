"""
每日模擬交易訊號檢查
------------------------
每天執行一次這支程式，它會：
  1. 抓最新的股價/幣價資料
  2. 判斷今天該「買進」「續抱」「賣出」還是「觀望」
  3. 把狀態存起來，明天執行時會記得今天的持倉狀況
  4. 把每天的判斷結果記錄到 paper_trading_log.csv，方便之後回顧

⚠️ 這支程式只給「建議」，不會真的幫你下單。
   看到建議後，你可以自己決定要不要照做、記錄下來，
   持續一段時間後再回頭比對「如果照做」跟實際策略預期的落差。

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

# ---------- 參數設定：跟回測用的是同一組，才有可比性 ----------
TICKER = "BTC-USD"          # 想追蹤的商品，先挑一個測試起的最有優勢的
SHORT_WINDOW = 20
LONG_WINDOW = 60
ATR_WINDOW = 14
ATR_MULTIPLIER = 3.0
RISK_PER_TRADE_PCT = 0.02
INITIAL_CAPITAL = 10000     # 假設的模擬帳戶總資金

STATE_FILE = "paper_trading_state.json"
LOG_FILE = "paper_trading_log.csv"


def fetch_recent_data(ticker):
    """抓最近約 400 天資料，足夠算出 60 日均線跟 ATR"""
    df = yf.download(ticker, period="400d", auto_adjust=True)
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


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"in_position": False}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def log_result(date, price, recommendation, in_position):
    file_exists = os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["日期", "商品", "收盤價", "持倉狀態", "建議"])
        writer.writerow([date, TICKER, f"{price:.2f}", "持倉中" if in_position else "空手", recommendation])


def main():
    df = fetch_recent_data(TICKER)
    df = generate_signals(df)
    latest = df.iloc[-1]
    price = latest["Close"]
    atr = latest["ATR"]
    today = df.index[-1].date()

    state = load_state()

    if not state.get("in_position", False):
        if latest["signal"] == 1:
            if pd.notna(atr):
                stop_distance_pct = (ATR_MULTIPLIER * atr) / price
                position_fraction = min(1.0, RISK_PER_TRADE_PCT / stop_distance_pct) if stop_distance_pct > 0 else 1.0
            else:
                position_fraction = 1.0

            recommendation = f"買進訊號出現！建議投入資金比例約 {position_fraction:.0%}（依目前波動性計算）"
            state = {
                "in_position": True,
                "entry_price": price,
                "entry_date": str(today),
                "highest_since_entry": price,
                "position_fraction": position_fraction,
            }
        else:
            recommendation = "空手觀望，尚未出現買進訊號（均線還沒黃金交叉）"
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
            recommendation = f"續抱。目前浮動損益 {current_return:.2%}，目前停損價位約 ${stop_price:.2f}"
            state["highest_since_entry"] = highest

    print(f"===== {TICKER} 每日訊號檢查 — {today} =====")
    print(f"收盤價: ${price:.2f}")
    print(f"判斷: {recommendation}")
    print()

    save_state(state)
    log_result(today, price, recommendation, state.get("in_position", False))
    print(f"已記錄到 {LOG_FILE}，可以打開 Excel 查看歷史紀錄")


if __name__ == "__main__":
    main()

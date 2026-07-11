"""
每日模擬交易訊號檢查（多商品版 + 批次抓取 + 報酬率記錄）
------------------------------------------------------------
每天執行一次，同時檢查多個商品的訊號：
  1. 批次抓取所有商品的最新資料
  2. 判斷每個商品該「買進」「續抱」「賣出」還是「觀望」
  3. 額外記錄「進場價」「浮動報酬」，讓儀表板能畫出報酬率追蹤圖
  4. 記錄到 paper_trading_log.csv

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
TICKERS = ["BTC-USD", "ETH-USD", "QQQ", "AAPL", "MSFT", "XOM", "PYPL", "INTC"]

SHORT_WINDOW = 20
LONG_WINDOW = 60
ATR_WINDOW = 14
ATR_MULTIPLIER = 3.0
RISK_PER_TRADE_PCT = 0.02

STATE_FILE = "paper_trading_state.json"
LOG_FILE = "paper_trading_log.csv"
LOG_HEADER = ["日期", "商品", "收盤價", "持倉狀態", "進場價", "浮動報酬", "建議"]


def fetch_batch_data(tickers):
    raw = yf.download(tickers, period="400d", auto_adjust=True, group_by="ticker", progress=False)
    data = {}
    for ticker in tickers:
        try:
            df = raw.copy() if len(tickers) == 1 else raw[ticker].copy()
            df = df[["High", "Low", "Close"]].dropna()
            if not df.empty:
                data[ticker] = df
        except Exception as e:
            print(f"⚠️ {ticker} 資料處理失敗，略過（原因: {e}）")
    return data


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


def ensure_log_schema():
    """確保 CSV 有正確的欄位結構；如果是舊版格式，自動遷移補上新欄位"""
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(LOG_HEADER)
        return

    with open(LOG_FILE, "r", encoding="utf-8-sig") as f:
        first_line = f.readline().strip()

    if first_line != ",".join(LOG_HEADER):
        df_old = pd.read_csv(LOG_FILE, encoding="utf-8-sig")
        for col in LOG_HEADER:
            if col not in df_old.columns:
                df_old[col] = ""
        df_old = df_old[LOG_HEADER]
        df_old.to_csv(LOG_FILE, index=False, encoding="utf-8-sig")
        print("已將舊版紀錄檔遷移為新格式（補上進場價/浮動報酬欄位）")


def log_result(date, ticker, price, entry_price, floating_return, recommendation, in_position):
    entry_str = f"{entry_price:.2f}" if entry_price is not None else ""
    return_str = f"{floating_return:.4f}" if floating_return is not None else ""
    with open(LOG_FILE, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([date, ticker, f"{price:.2f}", "持倉中" if in_position else "空手",
                          entry_str, return_str, recommendation])


def check_ticker(df, state):
    df = generate_signals(df)
    latest = df.iloc[-1]
    price = latest["Close"]
    atr = latest["ATR"]
    today = df.index[-1].date()
    entry_price_out, floating_return = None, None

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
            entry_price_out, floating_return = price, 0.0
        else:
            recommendation = "空手觀望，尚未出現買進訊號"
    else:
        entry_price = state["entry_price"]
        highest = max(state["highest_since_entry"], price)
        stop_price = highest - ATR_MULTIPLIER * atr if pd.notna(atr) else -np.inf
        stop_triggered = pd.notna(atr) and price <= stop_price
        ma_exit = latest["signal"] == 0
        current_return = price / entry_price - 1
        entry_price_out, floating_return = entry_price, current_return

        if stop_triggered or ma_exit:
            reason = "ATR停損" if stop_triggered else "均線死亡交叉"
            recommendation = f"賣出訊號！原因：{reason}，這筆交易報酬約 {current_return:.2%}"
            state = {"in_position": False}
        else:
            recommendation = f"續抱。浮動損益 {current_return:.2%}，目前停損價位約 ${stop_price:.2f}"
            state["highest_since_entry"] = highest

    return today, price, entry_price_out, floating_return, recommendation, state


def main():
    ensure_log_schema()
    all_state = load_all_state()

    print(f"===== 每日訊號檢查 — {datetime.now().strftime('%Y-%m-%d')} =====")
    print(f"批次抓取 {len(TICKERS)} 個商品的資料中...\n")

    batch_data = fetch_batch_data(TICKERS)

    for ticker in TICKERS:
        if ticker not in batch_data:
            print(f"【{ticker}】 資料抓取失敗，略過\n")
            continue

        ticker_state = all_state.get(ticker, {"in_position": False})
        today, price, entry_price, floating_return, recommendation, new_state = check_ticker(batch_data[ticker], ticker_state)
        all_state[ticker] = new_state

        print(f"【{ticker}】 收盤價: ${price:,.2f}")
        print(f"  判斷: {recommendation}\n")

        log_result(today, ticker, price, entry_price, floating_return, recommendation, new_state.get("in_position", False))

    save_all_state(all_state)
    print(f"已記錄到 {LOG_FILE}")


if __name__ == "__main__":
    main()

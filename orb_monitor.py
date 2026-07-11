"""
ORB 盤中監控程式（30分鐘 回測確認型，停利2R）
------------------------------------------------------
每次執行時，重新讀取「今天到目前為止」的5分鐘K棒，
重新判斷目前狀態：還沒開盤區間 / 等待突破 / 等待回測確認 / 持倉中 / 已出場

⚠️ 只給建議，不會真的幫你下單。

建議排程：美股開盤時段內，每5分鐘執行一次
    python orb_monitor.py
"""

import json
import os
import csv
from datetime import datetime, date

import pandas as pd
import yfinance as yf

# ---------- 參數設定（第一階段已驗證的最佳組合） ----------
TICKERS = ["QQQ", "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META",
           "INTC", "XOM", "JNJ", "KO", "PYPL", "DIS", "BA"]
OR_WINDOW_BARS = 6          # 30分鐘 = 6根5分鐘K棒
VARIANT = "回測確認型"
TAKE_PROFIT_R = 2.0
RETEST_TOLERANCE_PCT = 0.003
MIN_RISK_PCT = 0.001

STATE_FILE = "orb_state.json"
LOG_FILE = "orb_log.csv"
LOG_HEADER = ["時間", "商品", "方向", "事件", "價格", "R值", "備註"]


def fetch_today_data(ticker):
    df = yf.download(ticker, period="1d", interval="5m", auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close"]].dropna()
    return df


def evaluate_current_state(df_today, k, variant, direction, take_profit_r):
    """根據今天目前為止的資料，判斷這個方向現在處於哪個階段"""
    if len(df_today) < k + 1:
        return {"status": "尚未開盤足夠時間"}

    or_high = df_today["High"].iloc[:k].max()
    or_low = df_today["Low"].iloc[:k].min()
    remaining = df_today.iloc[k:]
    if remaining.empty:
        return {"status": "開盤區間已定義", "or_high": or_high, "or_low": or_low}

    level = or_high if direction == "long" else or_low
    breakout_mask = remaining["Close"] > or_high if direction == "long" else remaining["Close"] < or_low
    breakout_candidates = remaining[breakout_mask]
    if breakout_candidates.empty:
        return {"status": "尚未突破", "or_high": or_high, "or_low": or_low}
    breakout_idx = breakout_candidates.index[0]

    if variant == "標準型":
        entry_idx = breakout_idx
    else:
        after_breakout = remaining.loc[breakout_idx:].iloc[1:]
        tolerance = level * RETEST_TOLERANCE_PCT
        if direction == "long":
            retest_mask = (after_breakout["Low"] <= level + tolerance) & (after_breakout["Close"] > level)
        else:
            retest_mask = (after_breakout["High"] >= level - tolerance) & (after_breakout["Close"] < level)
        retest_candidates = after_breakout[retest_mask]
        if retest_candidates.empty:
            return {
                "status": "等待回測確認",
                "breakout_price": float(remaining.loc[breakout_idx, "Close"]),
                "breakout_time": str(breakout_idx),
            }
        entry_idx = retest_candidates.index[0]

    entry_price = float(remaining.loc[entry_idx, "Close"])
    stop_price = float(remaining.loc[entry_idx, "Low"] if direction == "long" else remaining.loc[entry_idx, "High"])
    risk = abs(entry_price - stop_price)
    if risk == 0 or (risk / entry_price) < MIN_RISK_PCT:
        return {"status": "訊號無效（停損距離過小）"}

    target_price = entry_price + take_profit_r * risk if direction == "long" else entry_price - take_profit_r * risk
    after_entry = remaining.loc[entry_idx:].iloc[1:]

    for idx, row in after_entry.iterrows():
        if direction == "long":
            if row["Low"] <= stop_price:
                return {"status": "已出場", "reason": "停損", "R": -1.0, "entry_price": entry_price,
                        "exit_price": stop_price, "entry_time": str(entry_idx), "exit_time": str(idx)}
            if row["High"] >= target_price:
                return {"status": "已出場", "reason": "停利", "R": take_profit_r, "entry_price": entry_price,
                        "exit_price": target_price, "entry_time": str(entry_idx), "exit_time": str(idx)}
        else:
            if row["High"] >= stop_price:
                return {"status": "已出場", "reason": "停損", "R": -1.0, "entry_price": entry_price,
                        "exit_price": stop_price, "entry_time": str(entry_idx), "exit_time": str(idx)}
            if row["Low"] <= target_price:
                return {"status": "已出場", "reason": "停利", "R": take_profit_r, "entry_price": entry_price,
                        "exit_price": target_price, "entry_time": str(entry_idx), "exit_time": str(idx)}

    current_price = float(remaining["Close"].iloc[-1])
    floating_r = (current_price - entry_price) / risk if direction == "long" else (entry_price - current_price) / risk
    return {"status": "持倉中", "entry_price": entry_price, "stop_price": stop_price,
            "target_price": target_price, "entry_time": str(entry_idx),
            "current_price": current_price, "floating_R": floating_r}


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def ensure_log_schema():
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(LOG_HEADER)


def log_event(ticker, direction, event, price, r_value, note):
    with open(LOG_FILE, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ticker, direction, event,
                          f"{price:.2f}" if price is not None else "", r_value if r_value is not None else "", note])


def main():
    ensure_log_schema()
    state = load_state()
    today_str = str(date.today())

    print(f"===== ORB 盤中監控 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} =====\n")

    for ticker in TICKERS:
        try:
            df_today = fetch_today_data(ticker)
        except Exception as e:
            print(f"⚠️ {ticker} 資料抓取失敗，略過（原因: {e}）")
            continue

        if df_today.empty:
            continue

        for direction in ["long", "short"]:
            key = f"{ticker}_{direction}"
            prev = state.get(key, {})

            # 換日了就重置這個方向的狀態
            if prev.get("date") != today_str:
                prev = {"date": today_str, "last_status": None}

            result = evaluate_current_state(df_today, OR_WINDOW_BARS, VARIANT, direction, TAKE_PROFIT_R)
            current_status = result["status"]

            dir_label = "做多" if direction == "long" else "做空"
            print(f"【{ticker} {dir_label}】 {current_status}")

            # 只在狀態「有意義地變化」時才記錄，避免每5分鐘都重複寫入一樣的內容
            if current_status != prev.get("last_status"):
                if current_status == "持倉中" and prev.get("last_status") != "持倉中":
                    log_event(ticker, dir_label, "進場", result["entry_price"], None,
                               f"停損 ${result['stop_price']:.2f} / 停利 ${result['target_price']:.2f}")
                    print(f"  🟢 新進場！進場價 ${result['entry_price']:.2f}")
                elif current_status == "已出場":
                    log_event(ticker, dir_label, f"出場（{result['reason']}）", result["exit_price"],
                               result["R"], f"進場價 ${result['entry_price']:.2f}")
                    print(f"  🔴 出場！原因: {result['reason']}，R值: {result['R']}")

            prev["last_status"] = current_status
            state[key] = prev

    save_state(state)
    print(f"\n狀態已更新，事件已記錄到 {LOG_FILE}")


if __name__ == "__main__":
    main()

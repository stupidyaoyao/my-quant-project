"""
均線系統 + moomoo 自動下單（模擬盤）
------------------------------------------
把 paper_trading_daily.py 的均線+ATR訊號，接上 moomoo 模擬帳戶真的下單。
每次要開新倉之前，一定先通過 risk_guard.pretrade_check()，沒通過就不下單。

⚠️ 這支程式會真的呼叫 moomoo 的下單API（但強制寫死是SIMULATE模擬環境）。
   執行前，moomoo OpenD 視窗必須保持開著、顯示 "Connected"。

執行方式：
    python moomoo_auto_trade.py
"""

import json
import os

import pandas as pd
import numpy as np
import yfinance as yf
import moomoo as ft

import risk_guard

# ---------- 參數設定（跟 paper_trading_daily.py 保持一致） ----------
TICKERS = ["QQQ", "AAPL", "MSFT", "INTC"]  # 先用少量幾支測試，確認沒問題再擴大
SHORT_WINDOW = 20
LONG_WINDOW = 60
ATR_WINDOW = 14
ATR_MULTIPLIER = 3.0
STRATEGY_NAME = "均線系統"

STATE_FILE = "moomoo_auto_trade_state.json"
OPEND_HOST = "127.0.0.1"
OPEND_PORT = 11111


def fetch_data(ticker):
    df = yf.download(ticker, period="400d", auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df[["High", "Low", "Close"]].dropna()


def generate_signals(df):
    df = df.copy()
    df["MA_short"] = df["Close"].rolling(SHORT_WINDOW).mean()
    df["MA_long"] = df["Close"].rolling(LONG_WINDOW).mean()
    df["signal"] = 0
    df.loc[df["MA_short"] > df["MA_long"], "signal"] = 1
    prev_close = df["Close"].shift(1)
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - prev_close).abs(),
                     (df["Low"] - prev_close).abs()], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(ATR_WINDOW).mean()
    return df


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_account_info(trd_ctx):
    """回傳 (acc_id, net_assets, current_position_count)"""
    ret, acc_list = trd_ctx.get_acc_list()
    if ret != ft.RET_OK:
        raise RuntimeError(f"讀取帳戶清單失敗: {acc_list}")
    sim_accounts = acc_list[acc_list["trd_env"] == "SIMULATE"]
    if sim_accounts.empty:
        raise RuntimeError("找不到模擬帳戶")
    acc_id = sim_accounts.iloc[0]["acc_id"]

    ret2, funds = trd_ctx.accinfo_query(trd_env=ft.TrdEnv.SIMULATE, acc_id=acc_id)
    if ret2 != ft.RET_OK:
        raise RuntimeError(f"讀取帳戶資金失敗: {funds}")
    net_assets = float(funds.iloc[0]["total_assets"])

    ret3, positions = trd_ctx.position_list_query(trd_env=ft.TrdEnv.SIMULATE, acc_id=acc_id)
    position_count = len(positions) if ret3 == ft.RET_OK else 0

    return acc_id, net_assets, position_count


def main():
    state = load_state()

    print("正在連線 moomoo OpenD...")
    trd_ctx = ft.OpenSecTradeContext(
        filter_trdmarket=ft.TrdMarket.US, host=OPEND_HOST, port=OPEND_PORT,
        security_firm=ft.SecurityFirm.FUTUSECURITIES,
    )

    try:
        acc_id, net_assets, position_count = get_account_info(trd_ctx)
        print(f"帳戶資產: ${net_assets:,.2f}，目前持倉數: {position_count}\n")

        for ticker in TICKERS:
            print(f"----- {ticker} -----")
            try:
                df = fetch_data(ticker)
                df = generate_signals(df)
            except Exception as e:
                print(f"⚠️ 資料抓取失敗，略過: {e}\n")
                continue

            latest = df.iloc[-1]
            price = latest["Close"]
            atr = latest["ATR"]
            ticker_state = state.get(ticker, {"in_position": False})

            if not ticker_state.get("in_position", False):
                if latest["signal"] != 1:
                    print("訊號: 空手觀望，不動作\n")
                    continue

                # ---------- 要開新倉了，先過風控檢查 ----------
                allowed, reasons = risk_guard.pretrade_check(STRATEGY_NAME, ticker, net_assets, position_count)
                if not allowed:
                    print(f"🚫 訊號出現，但風控攔下: {'; '.join(reasons)}\n")
                    continue

                stop_distance = ATR_MULTIPLIER * atr if pd.notna(atr) else price * 0.05
                stop_price = price - stop_distance
                qty = risk_guard.calculate_position_size(price, stop_price, net_assets)

                if qty <= 0:
                    print("⚠️ 計算出的部位數量為0，不下單\n")
                    continue

                print(f"✅ 通過風控，準備下單: 買進 {qty} 股 @ 市價（停損約${stop_price:.2f}）")
                ret, data = risk_guard.safe_place_order(trd_ctx, acc_id, f"US.{ticker}", qty, "long")
                if ret == ft.RET_OK:
                    print(f"下單成功: {data}\n")
                    state[ticker] = {
                        "in_position": True, "entry_price": price,
                        "highest_since_entry": price, "qty": qty,
                    }
                    risk_guard.record_trade(STRATEGY_NAME, net_assets)
                    position_count += 1
                else:
                    print(f"⚠️ 下單失敗: {data}\n")

            else:
                # ---------- 已持倉，檢查停損/均線出場（不需要過風控，出場永遠允許） ----------
                entry_price = ticker_state["entry_price"]
                highest = max(ticker_state["highest_since_entry"], price)
                stop_price = highest - ATR_MULTIPLIER * atr if pd.notna(atr) else -np.inf
                stop_triggered = pd.notna(atr) and price <= stop_price
                ma_exit = latest["signal"] == 0

                if stop_triggered or ma_exit:
                    reason = "ATR停損" if stop_triggered else "均線死亡交叉"
                    qty = ticker_state["qty"]
                    print(f"🔴 觸發出場（{reason}），準備賣出 {qty} 股")
                    ret, data = risk_guard.safe_place_order(trd_ctx, acc_id, f"US.{ticker}", qty, "short")
                    if ret == ft.RET_OK:
                        print(f"出場成功: {data}\n")
                        state[ticker] = {"in_position": False}
                    else:
                        print(f"⚠️ 出場下單失敗: {data}\n")
                else:
                    state[ticker]["highest_since_entry"] = highest
                    print(f"持倉中，續抱（目前價格 ${price:.2f}）\n")

        save_state(state)

    finally:
        trd_ctx.close()
        print("連線已關閉")


if __name__ == "__main__":
    main()

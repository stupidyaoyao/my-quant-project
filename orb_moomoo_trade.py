"""
ORB 當沖系統 + moomoo 自動下單（模擬盤）
------------------------------------------------
把 orb_monitor.py 的「30分鐘回測確認型」訊號，接上 moomoo 模擬帳戶真的下單。
設計給「開盤後2小時內」的短線當沖使用，需要搭配本機排程（不是GitHub Actions）。

⚠️ 執行前，moomoo OpenD 視窗必須保持開著、顯示 "Connected"。
⚠️ 這支程式只在美股開盤後2小時內執行才有意義，太晚執行會直接跳過。

股票清單改為動態：每天早上讀取 premarket_scanner.py 掃描出的「今日盤前爆量股」，
不再使用固定清單，天然跟均線系統的固定追蹤清單不重疊，
也更符合 ORB 抓「當天有動能的股票」這個策略特性。

執行方式（建議搭配 Windows工作排程器，每5分鐘跑一次）：
    python orb_moomoo_trade.py
"""

import json
import os
from datetime import datetime, time as dt_time

import pandas as pd
import yfinance as yf
import moomoo as ft
import pytz

import risk_guard

# ---------- 參數設定 ----------
MAX_WATCHLIST_SIZE = 8      # 篩選後最多留幾檔，避免每5分鐘要查太多檔拖慢速度
CANDIDATE_POOL_SIZE = 30    # 篩選前的候選池大小（合併盤前掃描+今日熱門後，篩到這個數量）
MIN_ATR_PCT = 0.02          # ATR至少要佔股價的2%，太安靜的股票對ORB沒有意義
FALLBACK_TICKERS = ["IWM"]  # 保底用小型股指數ETF，不重疊均線系統的QQQ/AAPL/MSFT/INTC
EXCLUDE_TICKERS = ["QQQ", "AAPL", "MSFT", "INTC"]  # 均線系統在用的股票，ORB明確排除，避免撞車
PREMARKET_FILE = "premarket_gappers.json"
OR_WINDOW_BARS = 6          # 30分鐘 = 6根5分鐘K棒
TAKE_PROFIT_R = 2.0
RETEST_TOLERANCE_PCT = 0.003
MIN_RISK_PCT = 0.001
STOCK_SLIPPAGE_PCT = 0.0005
STRATEGY_NAME = "ORB"

# 只在開盤後2小時內執行（美東時間 9:30-11:30）
MARKET_OPEN_TIME = dt_time(9, 30)
CUTOFF_TIME = dt_time(11, 30)
ET_TZ = pytz.timezone("America/New_York")

STATE_FILE = "orb_moomoo_state.json"
OPEND_HOST = "127.0.0.1"
OPEND_PORT = 11111


def compute_atr_pct(ticker, window=14):
    """算出這支股票的ATR佔股價的百分比，數字越大代表波動越劇烈"""
    try:
        df = yf.download(ticker, period="30d", interval="1d", auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if len(df) < window + 1:
            return None
        prev_close = df["Close"].shift(1)
        tr = pd.concat([
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(window).mean().iloc[-1]
        price = df["Close"].iloc[-1]
        return float(atr / price) if price > 0 else None
    except Exception:
        return None


def load_daily_watchlist():
    """
    合併「盤前爆量股掃描」+「今日交易量最活躍」兩個來源當候選池，
    再用ATR篩掉波動太小、對ORB沒意義的股票，依波動度排序取前幾名
    """
    candidates = []

    if os.path.exists(PREMARKET_FILE):
        try:
            with open(PREMARKET_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            candidates += [g["symbol"] for g in data.get("gappers", [])]
        except Exception as e:
            print(f"⚠️ 讀取盤前掃描結果失敗: {e}")

    try:
        result = yf.screen("most_actives", count=CANDIDATE_POOL_SIZE)
        candidates += [q["symbol"] for q in result.get("quotes", [])]
    except Exception as e:
        print(f"⚠️ 抓取今日熱門股失敗: {e}")

    candidates = list(dict.fromkeys(candidates))  # 去重，保留原本順序
    candidates = [t for t in candidates if t not in EXCLUDE_TICKERS]  # 排除均線系統在用的股票
    if not candidates:
        print(f"⚠️ 兩個來源都抓不到資料，使用保底清單: {FALLBACK_TICKERS}")
        return FALLBACK_TICKERS

    print(f"候選池共 {len(candidates)} 檔，開始用ATR篩選波動度...")
    scored = []
    for ticker in candidates:
        atr_pct = compute_atr_pct(ticker)
        if atr_pct is not None and atr_pct >= MIN_ATR_PCT:
            scored.append((ticker, atr_pct))

    if not scored:
        print(f"⚠️ 沒有股票通過ATR篩選（門檻{MIN_ATR_PCT:.0%}），使用保底清單: {FALLBACK_TICKERS}")
        return FALLBACK_TICKERS

    scored.sort(key=lambda x: x[1], reverse=True)
    watchlist = [t for t, _ in scored[:MAX_WATCHLIST_SIZE]]
    print(f"今日 ORB watchlist（依波動度排序）: {[(t, f'{a:.1%}') for t, a in scored[:MAX_WATCHLIST_SIZE]]}\n")
    return watchlist


def is_within_trading_window():
    now_et = datetime.now(ET_TZ)
    if now_et.weekday() >= 5:
        return False, "週末不交易"
    now_time = now_et.time()
    if now_time < MARKET_OPEN_TIME:
        return False, f"還沒開盤（現在美東時間 {now_time.strftime('%H:%M')}）"
    if now_time > CUTOFF_TIME:
        return False, f"已超過設定的2小時交易窗口（現在美東時間 {now_time.strftime('%H:%M')}）"
    return True, ""


def fetch_today_data(ticker):
    df = yf.download(ticker, period="1d", interval="5m", auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df[["Open", "High", "Low", "Close"]].dropna()


def evaluate_orb_signal(df_today):
    """回傳 None（沒訊號）或 dict（進場資訊）"""
    k = OR_WINDOW_BARS
    if len(df_today) < k + 1:
        return None
    or_high = df_today["High"].iloc[:k].max()
    remaining = df_today.iloc[k:]
    if remaining.empty:
        return None

    breakout_candidates = remaining[remaining["Close"] > or_high]
    if breakout_candidates.empty:
        return None
    breakout_idx = breakout_candidates.index[0]

    after_breakout = remaining.loc[breakout_idx:].iloc[1:]
    tolerance = or_high * RETEST_TOLERANCE_PCT
    retest_mask = (after_breakout["Low"] <= or_high + tolerance) & (after_breakout["Close"] > or_high)
    retest_candidates = after_breakout[retest_mask]
    if retest_candidates.empty:
        return None
    confirm_idx = retest_candidates.index[0]

    if confirm_idx != remaining.index[-1]:
        return None  # 只在剛確認的那一刻進場，不追已經過去的訊號

    entry_price = float(remaining.loc[confirm_idx, "Close"])
    stop_price = float(remaining.loc[confirm_idx, "Low"])
    risk = entry_price - stop_price
    if risk <= 0 or (risk / entry_price) < MIN_RISK_PCT:
        return None

    return {"entry_price": entry_price, "stop_price": stop_price, "risk": risk}


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_account_info(trd_ctx):
    ret, acc_list = trd_ctx.get_acc_list()
    if ret != ft.RET_OK:
        raise RuntimeError(f"讀取帳戶清單失敗: {acc_list}")
    sim_accounts = acc_list[acc_list["trd_env"] == "SIMULATE"]
    acc_id = sim_accounts.iloc[0]["acc_id"]
    ret2, funds = trd_ctx.accinfo_query(trd_env=ft.TrdEnv.SIMULATE, acc_id=acc_id)
    net_assets = float(funds.iloc[0]["total_assets"])
    ret3, positions = trd_ctx.position_list_query(trd_env=ft.TrdEnv.SIMULATE, acc_id=acc_id)
    position_count = len(positions) if ret3 == ft.RET_OK else 0

    # 可用現金 = 總資產 - 已經被現有持倉佔用的市值，避免部位計算誤用到已經花掉的錢
    holdings_value = 0.0
    if ret3 == ft.RET_OK and not positions.empty:
        try:
            holdings_value = float(positions["market_val"].astype(float).sum())
        except Exception as e:
            print(f"⚠️ 計算持倉市值失敗（{e}），可用現金暫時退回用總資產計算")
            holdings_value = 0.0
    available_cash = max(0.0, net_assets - holdings_value)

    return acc_id, net_assets, position_count, available_cash


def write_heartbeat(message):
    """不管有沒有進入交易時段，每次執行都留一筆紀錄，方便確認排程有沒有真的在跑"""
    with open("orb_scheduler_heartbeat.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")


def main():
    in_window, reason = is_within_trading_window()
    if not in_window:
        write_heartbeat(f"跳過（{reason}）")
        print(f"目前不在交易時段內，跳過本次執行（{reason}）")
        return

    write_heartbeat("開始執行交易邏輯")

    state = load_state()
    today_str = datetime.now(ET_TZ).strftime("%Y-%m-%d")
    tickers = load_daily_watchlist()

    print("正在連線 moomoo OpenD...")
    trd_ctx = ft.OpenSecTradeContext(
        filter_trdmarket=ft.TrdMarket.US, host=OPEND_HOST, port=OPEND_PORT,
        security_firm=ft.SecurityFirm.FUTUSECURITIES,
    )

    try:
        acc_id, net_assets, position_count, available_cash = get_account_info(trd_ctx)
        print(f"帳戶資產: ${net_assets:,.2f}，可用現金: ${available_cash:,.2f}，目前持倉數: {position_count}\n")

        for ticker in tickers:
            print(f"----- {ticker} -----")
            ticker_state = state.get(ticker, {})

            if ticker_state.get("date") != today_str:
                ticker_state = {"date": today_str, "in_position": False}

            if ticker_state.get("in_position"):
                print("已持倉中，本程式暫不處理出場（出場交給另一支停損監控程式）\n")
                state[ticker] = ticker_state
                continue

            try:
                df_today = fetch_today_data(ticker)
            except Exception as e:
                print(f"⚠️ 資料抓取失敗: {e}\n")
                continue

            signal = evaluate_orb_signal(df_today)
            if signal is None:
                print("尚無進場訊號\n")
                state[ticker] = ticker_state
                continue

            allowed, reasons = risk_guard.pretrade_check(STRATEGY_NAME, ticker, net_assets, position_count)
            if not allowed:
                print(f"🚫 訊號出現，但風控攔下: {'; '.join(reasons)}\n")
                state[ticker] = ticker_state
                continue

            qty = risk_guard.calculate_position_size(signal["entry_price"], signal["stop_price"], net_assets, available_cash)
            if qty <= 0:
                print("⚠️ 計算出的部位數量為0（可能是可用現金不足），不下單\n")
                continue

            print(f"✅ 通過風控，準備下單: 買進 {qty} 股 @ 市價（停損約${signal['stop_price']:.2f}，可用現金${available_cash:,.2f}）")
            ret, data = risk_guard.safe_place_order(trd_ctx, acc_id, f"US.{ticker}", qty, "long")
            if ret == ft.RET_OK:
                print(f"下單成功\n")
                ticker_state.update({
                    "in_position": True, "entry_price": signal["entry_price"],
                    "stop_price": signal["stop_price"], "qty": qty,
                })
                risk_guard.record_trade(STRATEGY_NAME, net_assets)
                position_count += 1
                available_cash -= qty * signal["entry_price"]  # 這次執行內，扣掉這筆已用掉的現金
            else:
                print(f"⚠️ 下單失敗: {data}\n")

            state[ticker] = ticker_state

        save_state(state)

    finally:
        trd_ctx.close()
        print("連線已關閉")


if __name__ == "__main__":
    main()

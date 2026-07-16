"""
每日模擬交易訊號檢查（多商品版 + 熱門股清單 + 新聞彙整）
------------------------------------------------------------
每天執行一次：
  1. 批次抓取「固定追蹤清單」+ Yahoo Finance「今日交易量最活躍」前25檔的資料
  2. 判斷每個商品該「買進」「續抱」「賣出」還是「觀望」
  3. 記錄進場價、浮動報酬，供儀表板畫報酬率圖
  4. 抓取所有追蹤商品的相關新聞，彙整成新聞牆資料

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
FIXED_TICKERS = ["BTC-USD", "ETH-USD", "QQQ", "AAPL", "MSFT", "XOM", "PYPL", "INTC"]
MOST_ACTIVE_COUNT = 25   # 只抓第一頁，約25檔

SHORT_WINDOW = 20
LONG_WINDOW = 60
ATR_WINDOW = 14
ATR_MULTIPLIER = 3.0
RISK_PER_TRADE_PCT = 0.02
STOCK_SLIPPAGE_PCT = 0.0005   # 股票/ETF滑價 0.05%
CRYPTO_SLIPPAGE_PCT = 0.001   # 加密貨幣滑價 0.1%（波動大、價差較寬）
NEWS_PER_TICKER = 3      # 每檔股票抓幾則新聞
NEWS_MAX_TOTAL = 40      # 新聞牆最多保留幾則

STATE_FILE = "paper_trading_state.json"
LOG_FILE = "paper_trading_log.csv"
NEWS_FILE = "news_log.json"
MOOMOO_WATCHLIST_FILE = "moomoo_watchlist.json"
LOG_HEADER = ["日期", "商品", "來源", "收盤價", "持倉狀態", "進場價", "浮動報酬", "建議"]


def fetch_most_active(count):
    """抓 Yahoo Finance 今日交易量最活躍清單，抓不到就回傳空清單，不影響其他功能"""
    try:
        result = yf.screen("most_actives", count=count)
        symbols = [q["symbol"] for q in result.get("quotes", [])]
        print(f"成功抓到 {len(symbols)} 檔今日熱門股: {symbols}\n")
        return symbols
    except Exception as e:
        print(f"⚠️ 抓取「今日熱門股」清單失敗，略過這部分（原因: {e}）\n")
        return []


def load_moomoo_watchlist():
    """讀取本機同步過來的moomoo追蹤清單，檔案不存在就回傳空清單"""
    if os.path.exists(MOOMOO_WATCHLIST_FILE):
        try:
            with open(MOOMOO_WATCHLIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            tickers = data.get("tickers", [])
            print(f"讀到 moomoo 追蹤清單: {tickers}\n")
            return tickers
        except Exception as e:
            print(f"⚠️ 讀取 moomoo 追蹤清單失敗: {e}\n")
    return []


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
                df_old[col] = "" if col != "來源" else "追蹤清單"
        df_old = df_old[LOG_HEADER]
        df_old.to_csv(LOG_FILE, index=False, encoding="utf-8-sig")
        print("已將舊版紀錄檔遷移為新格式\n")


def log_result(date, ticker, source, price, entry_price, floating_return, recommendation, in_position):
    entry_str = f"{entry_price:.2f}" if entry_price is not None else ""
    return_str = f"{floating_return:.4f}" if floating_return is not None else ""
    with open(LOG_FILE, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([date, ticker, source, f"{price:.2f}", "持倉中" if in_position else "空手",
                          entry_str, return_str, recommendation])


def check_ticker(ticker, df, state):
    df = generate_signals(df)
    latest = df.iloc[-1]
    price = latest["Close"]
    atr = latest["ATR"]
    today = df.index[-1].date()
    entry_price_out, floating_return = None, None
    slippage_pct = CRYPTO_SLIPPAGE_PCT if ticker.endswith("-USD") else STOCK_SLIPPAGE_PCT

    if not state.get("in_position", False):
        if latest["signal"] == 1:
            if pd.notna(atr):
                stop_distance_pct = (ATR_MULTIPLIER * atr) / price
                position_fraction = min(1.0, RISK_PER_TRADE_PCT / stop_distance_pct) if stop_distance_pct > 0 else 1.0
            else:
                position_fraction = 1.0
            # 買進滑價：實際成交價比顯示價格貴一點
            effective_entry_price = price * (1 + slippage_pct)
            recommendation = f"買進訊號！建議投入資金比例約 {position_fraction:.0%}（已計入滑價，實際成交約 ${effective_entry_price:.2f}）"
            state = {
                "in_position": True, "entry_price": effective_entry_price, "entry_date": str(today),
                "highest_since_entry": price, "position_fraction": position_fraction,
            }
            entry_price_out, floating_return = effective_entry_price, 0.0
        else:
            recommendation = "空手觀望，尚未出現買進訊號"
    else:
        entry_price = state["entry_price"]
        highest = max(state["highest_since_entry"], price)
        stop_price = highest - ATR_MULTIPLIER * atr if pd.notna(atr) else -np.inf
        stop_triggered = pd.notna(atr) and price <= stop_price
        ma_exit = latest["signal"] == 0
        # 持倉中的浮動損益：對比目前市價，還沒真的賣出，不套用滑價
        current_return = price / entry_price - 1
        entry_price_out, floating_return = entry_price, current_return

        if stop_triggered or ma_exit:
            reason = "ATR停損" if stop_triggered else "均線死亡交叉"
            # 賣出滑價：實際成交價比顯示價格便宜一點
            effective_exit_price = price * (1 - slippage_pct)
            realized_return = effective_exit_price / entry_price - 1
            recommendation = f"賣出訊號！原因：{reason}，這筆交易報酬約 {realized_return:.2%}（已計入滑價）"
            state = {"in_position": False}
            floating_return = realized_return
        else:
            recommendation = f"續抱。浮動損益 {current_return:.2%}，目前停損價位約 ${stop_price:.2f}"
            state["highest_since_entry"] = highest

    return today, price, entry_price_out, floating_return, recommendation, state


def fetch_news(tickers):
    """抓每檔股票的相關新聞，彙整、去重、依時間排序"""
    all_news = []
    seen_links = set()
    for ticker in tickers:
        try:
            items = yf.Ticker(ticker).news or []
        except Exception as e:
            print(f"⚠️ {ticker} 新聞抓取失敗，略過（原因: {e}）")
            continue

        for item in items[:NEWS_PER_TICKER]:
            content = item.get("content", item)  # 相容不同版本的資料結構
            link = content.get("canonicalUrl", {}).get("url") if isinstance(content.get("canonicalUrl"), dict) else content.get("link", "")
            title = content.get("title", "")
            if not link or link in seen_links or not title:
                continue
            seen_links.add(link)
            publisher = content.get("provider", {}).get("displayName", "") if isinstance(content.get("provider"), dict) else content.get("publisher", "")
            pub_time = content.get("pubDate") or content.get("providerPublishTime", "")
            all_news.append({
                "ticker": ticker, "title": title, "link": link,
                "publisher": publisher, "published": str(pub_time),
            })

    all_news.sort(key=lambda x: x["published"], reverse=True)
    all_news = all_news[:NEWS_MAX_TOTAL]
    with open(NEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(all_news, f, ensure_ascii=False, indent=2)
    print(f"已彙整 {len(all_news)} 則新聞到 {NEWS_FILE}\n")


def main():
    ensure_log_schema()
    all_state = load_all_state()

    most_active = fetch_most_active(MOST_ACTIVE_COUNT)
    moomoo_tickers = load_moomoo_watchlist()

    ticker_source = {t: "追蹤清單" for t in FIXED_TICKERS}
    for t in moomoo_tickers:
        if t not in ticker_source:
            ticker_source[t] = "moomoo清單"
    for t in most_active:
        if t not in ticker_source:
            ticker_source[t] = "今日熱門"

    all_tickers = list(ticker_source.keys())
    print(f"===== 每日訊號檢查 — {datetime.now().strftime('%Y-%m-%d')} =====")
    print(f"共 {len(all_tickers)} 個商品，批次抓取資料中...\n")

    batch_data = fetch_batch_data(all_tickers)

    for ticker in all_tickers:
        if ticker not in batch_data:
            print(f"【{ticker}】 資料抓取失敗，略過\n")
            continue

        ticker_state = all_state.get(ticker, {"in_position": False})
        today, price, entry_price, floating_return, recommendation, new_state = check_ticker(ticker, batch_data[ticker], ticker_state)
        all_state[ticker] = new_state

        print(f"【{ticker}】({ticker_source[ticker]}) 收盤價: ${price:,.2f}")
        print(f"  判斷: {recommendation}\n")

        log_result(today, ticker, ticker_source[ticker], price, entry_price, floating_return,
                    recommendation, new_state.get("in_position", False))

    save_all_state(all_state)
    print(f"已記錄到 {LOG_FILE}\n")

    fetch_news(all_tickers)


if __name__ == "__main__":
    main()

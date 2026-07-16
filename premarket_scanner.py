"""
盤前爆量股掃描器
------------------------
篩選條件：漲幅>5%、股價>$3、盤前成交量>5萬股，取前10名，
並附上每支股票的新聞/上漲原因。

用 yfinance 的內建功能，取代直接爬 Yahoo/Benzinga 網頁，比較穩定。

⚠️ 盤前資料只有在真正的美股盤前時段（美東時間約4:00-9:30am）執行才會有意義，
   其他時段執行，程式會自動退回用「當日漲跌幅」估算，並在輸出裡標註。

執行方式：
    python premarket_scanner.py
"""

import json
from datetime import datetime

import yfinance as yf

MIN_GAP_PCT = 5.0
MIN_PRICE = 3.0
MIN_PREMARKET_VOLUME = 50000
TOP_N = 10
CANDIDATE_POOL_SIZE = 50
OUTPUT_FILE = "premarket_gappers.json"


def fetch_candidates():
    """先用漲幅榜篩選出候選名單，再逐一檢查是否符合盤前條件"""
    try:
        result = yf.screen("day_gainers", count=CANDIDATE_POOL_SIZE)
        symbols = [q["symbol"] for q in result.get("quotes", [])]
        print(f"抓到 {len(symbols)} 檔候選股票\n")
        return symbols
    except Exception as e:
        print(f"⚠️ 抓取候選清單失敗: {e}\n")
        return []


def get_gap_info(ticker):
    """優先使用盤前資料；沒有盤前資料時，退回用當日漲跌幅估算"""
    try:
        info = yf.Ticker(ticker).info
        premarket_price = info.get("preMarketPrice")
        prev_close = info.get("regularMarketPreviousClose") or info.get("previousClose")
        premarket_volume = info.get("preMarketVolume") or 0
        regular_price = info.get("regularMarketPrice") or info.get("currentPrice")

        if premarket_price and prev_close:
            gap_pct = (premarket_price / prev_close - 1) * 100
            return {
                "price": premarket_price, "gap_pct": gap_pct,
                "premarket_volume": premarket_volume, "is_premarket_data": True,
            }
        else:
            change_pct = info.get("regularMarketChangePercent")
            return {
                "price": regular_price, "gap_pct": change_pct,
                "premarket_volume": info.get("regularMarketVolume") or 0,
                "is_premarket_data": False,
            }
    except Exception as e:
        print(f"⚠️ {ticker} 讀取失敗: {e}")
        return None


def fetch_catalyst(ticker):
    """抓最新1-2則新聞當作上漲原因參考"""
    try:
        news_items = yf.Ticker(ticker).news or []
        headlines = []
        for item in news_items[:2]:
            content = item.get("content", item)
            title = content.get("title", "")
            if title:
                headlines.append(title)
        catalyst = headlines[0] if headlines else None
        return catalyst, headlines
    except Exception:
        return None, []


def main():
    candidates = fetch_candidates()
    results = []

    for ticker in candidates:
        info = get_gap_info(ticker)
        if info is None or info["price"] is None or info["gap_pct"] is None:
            continue
        if info["price"] <= MIN_PRICE:
            continue
        if info["gap_pct"] <= MIN_GAP_PCT:
            continue
        if info["premarket_volume"] < MIN_PREMARKET_VOLUME:
            continue
        results.append({"symbol": ticker, **info})

    results.sort(key=lambda x: x["gap_pct"], reverse=True)
    top_results = results[:TOP_N]

    gappers = []
    for rank, r in enumerate(top_results, start=1):
        catalyst, headlines = fetch_catalyst(r["symbol"])
        gappers.append({
            "rank": rank,
            "symbol": r["symbol"],
            "price": round(r["price"], 2),
            "gap_pct": round(r["gap_pct"], 2),
            "premarket_volume": int(r["premarket_volume"]),
            "is_premarket_data": r["is_premarket_data"],
            "catalyst": catalyst,
            "headlines": headlines,
        })

    output = {"scanned_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "gappers": gappers}
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    if gappers:
        summary_parts = [
            f"{g['symbol']} ({g['gap_pct']:+.1f}%)" + (f" — {g['catalyst']}" if g["catalyst"] else "")
            for g in gappers[:3]
        ]
        print(f"Premarket Gappers: {len(gappers)} 檔. Top: " + ", ".join(summary_parts))
    else:
        print("沒有符合條件的盤前爆量股")


if __name__ == "__main__":
    main()

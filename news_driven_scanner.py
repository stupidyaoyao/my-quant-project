"""
新聞驅動候選股票掃描器
------------------------
跟 premarket_scanner.py 的邏輯相反：
premarket_scanner 是「先看漲幅，才查新聞原因」
這支程式是「先掃新聞，不管股價現在有沒有動」，用來發現平常不會主動注意到的機會。

做法：
1. 抓大盤指數（S&P500、道瓊、那斯達克）層級的新聞（不綁定特定股票）
2. 用一份S&P500成分股清單，比對新聞標題/摘要裡有沒有提到這些公司
3. 統計「今天被提到最多次」的股票，輸出成候選清單

⚠️ 這是關鍵字比對，不是真正的AI語意理解，公司名稱比對可能有漏抓或誤判，
   這是v1版本，先求能用，之後可以再優化比對的準確度。

執行方式：
    python news_driven_scanner.py
"""

import json
import re
from collections import Counter
from datetime import datetime

import yfinance as yf

# 大盤指數，用來抓「不綁定特定股票」的大盤新聞
MARKET_INDEXES = ["^GSPC", "^DJI", "^IXIC"]
OUTPUT_FILE = "news_driven_candidates.json"
TOP_N = 10
MAX_NEWS_PER_INDEX = 30


def load_sp500_reference():
    """
    抓一份S&P500成分股清單當比對基準（代號+公司名稱）。
    用維基百科的公開表格，這是最容易取得、免費、不需要API金鑰的方式。
    """
    try:
        import io
        import pandas as pd
        import requests
        headers = {"User-Agent": "Mozilla/5.0 (compatible; my-quant-project research script)"}
        resp = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", headers=headers, timeout=15)
        resp.raise_for_status()
        tables = pd.read_html(io.StringIO(resp.text))
        df = tables[0]
        ref = {}
        for _, row in df.iterrows():
            symbol = str(row.get("Symbol", "")).strip().replace(".", "-")
            name = str(row.get("Security", "")).strip()
            if symbol and name:
                ref[symbol] = name
        return ref
    except Exception as e:
        print(f"⚠️ 抓取S&P500清單失敗: {e}")
        return {}


def fetch_market_news():
    """抓大盤指數層級的新聞"""
    all_news = []
    for idx in MARKET_INDEXES:
        try:
            news_items = yf.Ticker(idx).news or []
            all_news.extend(news_items[:MAX_NEWS_PER_INDEX])
        except Exception as e:
            print(f"⚠️ 抓取 {idx} 新聞失敗: {e}")
    return all_news


def extract_mentions(news_items, sp500_ref):
    """
    在新聞標題+摘要裡，比對S&P500公司名稱/代號有沒有被提到，
    用「完整單字比對」避免誤判（例如太短的代號容易在一般文字裡誤中）
    """
    mention_counter = Counter()
    mention_examples = {}

    for item in news_items:
        content = item.get("content", item)
        title = content.get("title", "") or ""
        summary = content.get("summary", "") or content.get("description", "") or ""
        text = f"{title} {summary}"

        for symbol, name in sp500_ref.items():
            if len(symbol) >= 3 and re.search(rf"\b{re.escape(symbol)}\b", text):
                mention_counter[symbol] += 1
                mention_examples.setdefault(symbol, title)
                continue
            name_core = re.sub(r"\s+(Inc\.?|Corp\.?|Corporation|Company|Co\.?|Ltd\.?|plc)$", "", name, flags=re.I).strip()
            if name_core and len(name_core) >= 4 and re.search(re.escape(name_core), text, re.I):
                mention_counter[symbol] += 1
                mention_examples.setdefault(symbol, title)

    return mention_counter, mention_examples


def main():
    print("正在抓取S&P500參考清單...")
    sp500_ref = load_sp500_reference()
    if not sp500_ref:
        print("⚠️ 沒有參考清單，無法比對，程式結束")
        return
    print(f"取得 {len(sp500_ref)} 家公司當比對基準\n")

    print("正在抓取大盤新聞...")
    news_items = fetch_market_news()
    print(f"共抓到 {len(news_items)} 則新聞\n")

    if not news_items:
        print("⚠️ 沒有抓到任何新聞")
        return

    print("正在比對新聞裡提到的公司...")
    mention_counter, mention_examples = extract_mentions(news_items, sp500_ref)

    top_candidates = mention_counter.most_common(TOP_N)

    output = {
        "scanned_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "news_count": len(news_items),
        "candidates": [
            {
                "symbol": symbol,
                "company_name": sp500_ref.get(symbol, ""),
                "mention_count": count,
                "example_headline": mention_examples.get(symbol, ""),
            }
            for symbol, count in top_candidates
        ],
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    if top_candidates:
        print(f"\n今日新聞熱度候選（前{TOP_N}名）:")
        for symbol, count in top_candidates:
            print(f"  {symbol} ({sp500_ref.get(symbol, '')}): 被提到{count}次 — \"{mention_examples.get(symbol, '')}\"")
    else:
        print("今天沒有比對到任何S&P500公司被新聞提及")


if __name__ == "__main__":
    main()

"""
新聞牆頁面（簡潔清單版）
------------------------
顯示所有追蹤商品的相關新聞，時間顯示為「幾分鐘前」，
標題直接可點擊連到原文，排版參考股票報價網站的新聞清單風格。
"""

import json
import os
from datetime import datetime, timezone

import streamlit as st

from common import inject_base_css

inject_base_css()
st.title("相關新聞")

NEWS_FILE = "news_log.json"

if not os.path.exists(NEWS_FILE):
    st.warning("還沒有新聞資料，請先執行 python paper_trading_daily.py 產生資料")
    st.stop()

with open(NEWS_FILE, "r", encoding="utf-8") as f:
    news_list = json.load(f)

if not news_list:
    st.info("目前沒有抓到任何新聞")
    st.stop()


def parse_time_ago(published):
    """把 unix timestamp 或 ISO 日期字串，轉換成「幾分鐘/小時/天前」"""
    if not published:
        return ""
    dt = None
    try:
        dt = datetime.fromtimestamp(float(published), tz=timezone.utc)
    except (ValueError, TypeError):
        try:
            s = str(published).replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return ""

    if dt is None:
        return ""

    delta = datetime.now(timezone.utc) - dt
    seconds = delta.total_seconds()
    if seconds < 60:
        return "剛剛"
    elif seconds < 3600:
        return f"{int(seconds // 60)}分鐘前"
    elif seconds < 86400:
        return f"{int(seconds // 3600)}小時前"
    else:
        return f"{int(seconds // 86400)}天前"


all_tickers = sorted(set(n["ticker"] for n in news_list))
with st.sidebar.expander("篩選", expanded=False):
    selected = st.multiselect("依商品篩選新聞", all_tickers, default=all_tickers)

filtered_news = [n for n in news_list if n["ticker"] in selected]
st.caption(f"共 {len(filtered_news)} 則新聞")
st.markdown("---")

for item in filtered_news:
    time_ago = parse_time_ago(item.get("published", ""))
    title = item["title"]
    link = item["link"]
    ticker = item["ticker"]

    st.markdown(
        f"""<div style="display:flex;align-items:baseline;gap:14px;padding:8px 0;">
        <div style="flex:0 0 70px;color:#888;font-size:0.85em;">{time_ago}</div>
        <div style="flex:1;">
            <a href="{link}" target="_blank" style="color:#6366f1;text-decoration:none;font-weight:500;">{title}</a>
            <span style="color:#888;font-size:0.8em;margin-left:8px;">· {ticker}</span>
        </div>
        </div>
        <hr style="margin:2px 0;opacity:0.1;">""",
        unsafe_allow_html=True,
    )

"""
新聞牆頁面
------------------------
顯示所有追蹤商品的相關新聞，每篇新聞會標示是哪支股票/幣的。
資料來源：paper_trading_daily.py 執行時彙整的 news_log.json

這個檔案要放在 pages/ 資料夾裡，Streamlit 會自動把它變成側邊選單裡的分頁。
"""

import json
import os
from datetime import datetime

import streamlit as st

st.set_page_config(page_title="新聞牆", layout="wide")
st.title("📰 相關新聞牆")

NEWS_FILE = "news_log.json"

if not os.path.exists(NEWS_FILE):
    st.warning("還沒有新聞資料，請先執行 python paper_trading_daily.py 產生資料")
    st.stop()

with open(NEWS_FILE, "r", encoding="utf-8") as f:
    news_list = json.load(f)

if not news_list:
    st.info("目前沒有抓到任何新聞")
    st.stop()

all_tickers = sorted(set(n["ticker"] for n in news_list))
st.sidebar.header("篩選")
selected = st.sidebar.multiselect("依商品篩選新聞", all_tickers, default=all_tickers)

filtered_news = [n for n in news_list if n["ticker"] in selected]
st.caption(f"共 {len(filtered_news)} 則新聞")

for item in filtered_news:
    published = item.get("published", "")
    try:
        # 如果是 unix timestamp，轉換成可讀時間
        published_display = datetime.fromtimestamp(float(published)).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        published_display = published

    st.markdown(
        f"""**[{item['title']}]({item['link']})**
        🏷️ `{item['ticker']}`  ·  {item.get('publisher', '')}  ·  {published_display}"""
    )
    st.divider()

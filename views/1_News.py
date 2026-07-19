"""相關新聞（函式化版本，供 app.py 路由器呼叫）"""

import json
import os
from datetime import datetime, timezone

import streamlit as st


def parse_time_ago(published):
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
    seconds = (datetime.now(timezone.utc) - dt).total_seconds()
    if seconds < 60:
        return "剛剛"
    elif seconds < 3600:
        return f"{int(seconds // 60)}分鐘前"
    elif seconds < 86400:
        return f"{int(seconds // 3600)}小時前"
    return f"{int(seconds // 86400)}天前"


def render_news():
    st.title("相關新聞")

    NEWS_FILE = "news_log.json"
    if not os.path.exists(NEWS_FILE):
        st.warning("還沒有新聞資料，請先執行 python paper_trading_daily.py 產生資料")
        return

    with open(NEWS_FILE, "r", encoding="utf-8") as f:
        news_list = json.load(f)
    if not news_list:
        st.info("目前沒有抓到任何新聞")
        return

    all_tickers = sorted(set(n["ticker"] for n in news_list))
    with st.sidebar.expander("篩選", expanded=False):
        selected = st.multiselect("依商品篩選新聞", all_tickers, default=all_tickers)

    filtered_news = [n for n in news_list if n["ticker"] in selected]
    st.caption(f"共 {len(filtered_news)} 則新聞")
    st.markdown("---")

    for item in filtered_news:
        time_ago = parse_time_ago(item.get("published", ""))
        st.markdown(
            f"""<div style="display:flex;align-items:baseline;gap:14px;padding:8px 0;">
            <div style="flex:0 0 70px;color:#888;font-size:0.85em;">{time_ago}</div>
            <div style="flex:1;">
                <a href="{item['link']}" target="_blank" style="color:#6366f1;text-decoration:none;font-weight:500;">{item['title']}</a>
                <span style="color:#888;font-size:0.8em;margin-left:8px;">· {item['ticker']}</span>
            </div>
            </div>
            <hr style="margin:2px 0;opacity:0.1;">""",
            unsafe_allow_html=True,
        )

"""
模擬交易儀表板（本機網頁）
------------------------------
用瀏覽器查看每日訊號紀錄，取代打開 Excel 看 CSV。

安裝（只需要跑一次）：
    pip install streamlit

執行方式：
    streamlit run dashboard.py

執行後會自動在瀏覽器開啟 http://localhost:8501
每次執行完 paper_trading_daily.py 產生新資料後，
回到瀏覽器分頁按重新整理（F5）就能看到最新資料。
"""

import os
import pandas as pd
import streamlit as st

st.set_page_config(page_title="量化交易模擬儀表板", layout="wide")
st.title("📈 模擬交易每日追蹤儀表板")

LOG_FILE = "paper_trading_log.csv"

if not os.path.exists(LOG_FILE):
    st.warning("還沒有任何紀錄，請先在終端機執行 python paper_trading_daily.py 產生資料")
    st.stop()

df = pd.read_csv(LOG_FILE, encoding="utf-8-sig")
df["日期"] = pd.to_datetime(df["日期"])
df["收盤價"] = pd.to_numeric(df["收盤價"], errors="coerce")

tickers = df["商品"].unique().tolist()

st.sidebar.header("篩選商品")
selected_tickers = st.sidebar.multiselect("選擇要顯示的商品", tickers, default=tickers)

filtered = df[df["商品"].isin(selected_tickers)].sort_values("日期")

# ---------- 今日最新狀態卡片 ----------
st.subheader("今日最新狀態")
if selected_tickers:
    cols = st.columns(len(selected_tickers))
    for col, ticker in zip(cols, selected_tickers):
        latest_row = df[df["商品"] == ticker].sort_values("日期").iloc[-1]
        with col:
            st.metric(label=ticker, value=f"${latest_row['收盤價']:,.2f}", delta=latest_row["持倉狀態"])
            st.caption(latest_row["建議"])

st.divider()

# ---------- 價格走勢圖 ----------
st.subheader("價格走勢")
for ticker in selected_tickers:
    t_df = filtered[filtered["商品"] == ticker].set_index("日期")["收盤價"]
    if len(t_df) >= 2:
        st.line_chart(t_df, height=250, use_container_width=True)
    st.caption(f"{ticker}（累積 {len(t_df)} 筆紀錄）")

st.divider()

# ---------- 歷史紀錄表格 ----------
st.subheader("歷史判斷紀錄")
st.dataframe(
    filtered.sort_values("日期", ascending=False),
    use_container_width=True,
    hide_index=True,
)

"""
歷史判斷紀錄頁面（獨立分頁）
------------------------------
從主頁面搬出來，附上日期快篩按鈕：今日/本周/本月/今年/全部
"""

import pandas as pd
import streamlit as st

from common import inject_base_css, load_log

st.set_page_config(page_title="歷史紀錄", layout="wide")
inject_base_css()
st.title("📋 歷史判斷紀錄")

df = load_log()
if df is None:
    st.warning("還沒有任何紀錄，請先執行 python paper_trading_daily.py 產生資料")
    st.stop()

tickers = df["商品"].unique().tolist()
with st.sidebar.expander("🔍 篩選", expanded=False):
    selected_tickers = st.multiselect("選擇要顯示的商品", tickers, default=tickers)

date_filter = st.radio(
    "時間範圍", ["今日", "本周", "本月", "今年", "全部"],
    horizontal=True, index=4,
)

now = pd.Timestamp.now().normalize()
if date_filter == "今日":
    start_date = now
elif date_filter == "本周":
    start_date = now - pd.Timedelta(days=now.dayofweek)
elif date_filter == "本月":
    start_date = now.replace(day=1)
elif date_filter == "今年":
    start_date = now.replace(month=1, day=1)
else:
    start_date = None

filtered = df[df["商品"].isin(selected_tickers)]
if start_date is not None:
    filtered = filtered[filtered["日期"] >= start_date]

filtered = filtered.sort_values("日期", ascending=False)
st.caption(f"共 {len(filtered)} 筆紀錄")
st.dataframe(filtered, width='stretch', hide_index=True)

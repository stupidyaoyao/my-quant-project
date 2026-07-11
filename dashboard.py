"""
模擬交易儀表板（本機網頁 / 雲端部署）
------------------------------------------
新增功能：
  - 依商品類型分組顯示（加密貨幣 / 股票）
  - 持倉中的商品用綠色框特別標示
  - 報酬率追蹤圖表

執行方式：
    streamlit run dashboard.py
"""

import os
import pandas as pd
import streamlit as st

st.set_page_config(page_title="量化交易模擬儀表板", layout="wide")
st.title("📈 模擬交易每日追蹤儀表板")

LOG_FILE = "paper_trading_log.csv"

if not os.path.exists(LOG_FILE):
    st.warning("還沒有任何紀錄，請先執行 python paper_trading_daily.py 產生資料")
    st.stop()

df = pd.read_csv(LOG_FILE, encoding="utf-8-sig")
df["日期"] = pd.to_datetime(df["日期"])
df["收盤價"] = pd.to_numeric(df["收盤價"], errors="coerce")
if "浮動報酬" in df.columns:
    df["浮動報酬"] = pd.to_numeric(df["浮動報酬"], errors="coerce")
else:
    df["浮動報酬"] = pd.NA


def classify(ticker):
    return "加密貨幣" if str(ticker).endswith("-USD") else "股票"


df["類型"] = df["商品"].apply(classify)
tickers = df["商品"].unique().tolist()

st.sidebar.header("篩選")
selected_tickers = st.sidebar.multiselect("選擇要顯示的商品", tickers, default=tickers)
filtered = df[df["商品"].isin(selected_tickers)].sort_values("日期")

# ---------- 今日最新狀態（依類型分組，持倉中特別標示） ----------
st.subheader("今日最新狀態")

for group_name, emoji in [("加密貨幣", "🪙"), ("股票", "📊")]:
    group_tickers = [t for t in selected_tickers if classify(t) == group_name]
    if not group_tickers:
        continue
    st.markdown(f"#### {emoji} {group_name}")
    cols = st.columns(len(group_tickers))
    for col, ticker in zip(cols, group_tickers):
        latest_row = df[df["商品"] == ticker].sort_values("日期").iloc[-1]
        holding = latest_row["持倉狀態"] == "持倉中"
        with col:
            if holding:
                st.markdown(
                    f"""<div style="border:2px solid #2ecc71;border-radius:10px;padding:12px;
                    background-color:rgba(46,204,113,0.10);">
                    <b>🟢 {ticker}</b><br>
                    <span style="font-size:1.2em;">${latest_row['收盤價']:,.2f}</span><br>
                    <span style="color:#2ecc71;font-weight:bold;">持倉中</span>
                    </div>""",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"""<div style="border:1px solid #444;border-radius:10px;padding:12px;">
                    <b>{ticker}</b><br>
                    <span style="font-size:1.2em;">${latest_row['收盤價']:,.2f}</span><br>
                    <span style="color:#888;">空手</span>
                    </div>""",
                    unsafe_allow_html=True,
                )
            st.caption(latest_row["建議"])

st.divider()

# ---------- 報酬率追蹤 ----------
st.subheader("💰 報酬率追蹤")
has_return_data = filtered["浮動報酬"].notna().any()
if has_return_data:
    return_tickers = [t for t in selected_tickers if filtered[filtered["商品"] == t]["浮動報酬"].notna().any()]
    for ticker in return_tickers:
        t_df = filtered[(filtered["商品"] == ticker) & (filtered["浮動報酬"].notna())]
        if len(t_df) >= 1:
            series = t_df.set_index("日期")["浮動報酬"] * 100
            st.line_chart(series, height=200, use_container_width=True)
            latest_return = series.iloc[-1]
            color = "🟢" if latest_return >= 0 else "🔴"
            st.caption(f"{ticker} 浮動報酬率 (%) — 目前 {color} {latest_return:.2f}%")
else:
    st.info("目前還沒有持倉紀錄可以追蹤報酬率（尚未出現買進訊號，或使用的是舊版紀錄檔）")

st.divider()

# ---------- 價格走勢 ----------
st.subheader("📈 價格走勢")
for ticker in selected_tickers:
    t_df = filtered[filtered["商品"] == ticker].set_index("日期")["收盤價"]
    if len(t_df) >= 2:
        st.line_chart(t_df, height=220, use_container_width=True)
    st.caption(ticker)

st.divider()

# ---------- 歷史紀錄表格 ----------
st.subheader("📋 歷史判斷紀錄")
st.dataframe(filtered.sort_values("日期", ascending=False), use_container_width=True, hide_index=True)

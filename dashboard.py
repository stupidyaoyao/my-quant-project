"""
模擬交易儀表板 — 主頁面
------------------------------
- 依來源與類型分組（加密貨幣/股票/今日熱門股）
- 持倉中優先顯示，空手觀望超過5個自動收合
- 點擊商品卡片下方按鈕，可查看K線圖

執行方式：
    streamlit run dashboard.py
"""

import os
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
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
for col in ["浮動報酬", "來源"]:
    if col not in df.columns:
        df[col] = "" if col == "來源" else pd.NA
df["來源"] = df["來源"].replace("", "追蹤清單").fillna("追蹤清單")


def classify(ticker):
    return "加密貨幣" if str(ticker).endswith("-USD") else "股票"


df["類型"] = df["商品"].apply(classify)
tickers = df["商品"].unique().tolist()

st.sidebar.header("篩選")
selected_tickers = st.sidebar.multiselect("選擇要顯示的商品", tickers, default=tickers)

if "selected_chart_ticker" not in st.session_state:
    st.session_state.selected_chart_ticker = None


def render_card(ticker):
    latest_row = df[df["商品"] == ticker].sort_values("日期").iloc[-1]
    holding = latest_row["持倉狀態"] == "持倉中"
    if holding:
        st.markdown(
            f"""<div style="border:2px solid #2ecc71;border-radius:10px;padding:10px;
            background-color:rgba(46,204,113,0.10);min-height:95px;">
            <b>🟢 {ticker}</b><br>
            <span style="font-size:1.1em;">${latest_row['收盤價']:,.2f}</span><br>
            <span style="color:#2ecc71;font-weight:bold;font-size:0.85em;">持倉中</span>
            </div>""",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""<div style="border:1px solid #444;border-radius:10px;padding:10px;min-height:95px;">
            <b>{ticker}</b><br>
            <span style="font-size:1.1em;">${latest_row['收盤價']:,.2f}</span><br>
            <span style="color:#888;font-size:0.85em;">空手</span>
            </div>""",
            unsafe_allow_html=True,
        )
    if st.button(f"📊 看K線圖", key=f"chart_btn_{ticker}", width='stretch'):
        st.session_state.selected_chart_ticker = ticker


def render_grid(ticker_list, n_cols=5):
    """把商品清單切成每列 n_cols 個，用水平排列的卡片顯示"""
    for i in range(0, len(ticker_list), n_cols):
        row_tickers = ticker_list[i:i + n_cols]
        cols = st.columns(n_cols)
        for col, ticker in zip(cols, row_tickers):
            with col:
                render_card(ticker)


def render_group(title, emoji, group_tickers):
    if not group_tickers:
        return
    st.markdown(f"#### {emoji} {title}")

    latest_by_ticker = {t: df[df["商品"] == t].sort_values("日期").iloc[-1] for t in group_tickers}
    holding_list = [t for t in group_tickers if latest_by_ticker[t]["持倉狀態"] == "持倉中"]
    watching_list = [t for t in group_tickers if t not in holding_list]

    if holding_list:
        render_grid(holding_list, n_cols=5)

    if watching_list:
        if len(watching_list) <= 5:
            render_grid(watching_list, n_cols=5)
        else:
            render_grid(watching_list[:5], n_cols=5)
            with st.expander(f"更多（還有 {len(watching_list) - 5} 個空手觀望中）"):
                render_grid(watching_list[5:], n_cols=5)
    st.markdown("")


st.subheader("今日最新狀態")

watchlist_tickers = df[df["來源"] == "追蹤清單"]["商品"].unique().tolist()
hot_tickers = df[df["來源"] == "今日熱門"]["商品"].unique().tolist()

crypto_tickers = [t for t in selected_tickers if t in watchlist_tickers and classify(t) == "加密貨幣"]
stock_tickers = [t for t in selected_tickers if t in watchlist_tickers and classify(t) == "股票"]
hot_selected = [t for t in selected_tickers if t in hot_tickers]

render_group("加密貨幣", "🪙", crypto_tickers)
render_group("股票（追蹤清單）", "📊", stock_tickers)
render_group("今日熱門股（Yahoo Most Active）", "🔥", hot_selected)

# ---------- K線圖區塊：點擊上方任一「看K線圖」按鈕後顯示 ----------
if st.session_state.selected_chart_ticker:
    ticker = st.session_state.selected_chart_ticker
    st.divider()
    st.subheader(f"🕯️ {ticker} K線圖（近6個月）")
    with st.spinner(f"抓取 {ticker} 資料中..."):
        try:
            candle_df = yf.download(ticker, period="6mo", auto_adjust=True, progress=False)
            if isinstance(candle_df.columns, pd.MultiIndex):
                candle_df.columns = candle_df.columns.get_level_values(0)
            fig = go.Figure(data=[go.Candlestick(
                x=candle_df.index,
                open=candle_df["Open"], high=candle_df["High"],
                low=candle_df["Low"], close=candle_df["Close"],
            )])
            fig.update_layout(xaxis_rangeslider_visible=False, height=450,
                               margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, width='stretch')
            if st.button("關閉K線圖"):
                st.session_state.selected_chart_ticker = None
                st.rerun()
        except Exception as e:
            st.error(f"抓取K線圖失敗: {e}")

st.divider()

# ---------- 歷史紀錄表格 ----------
st.subheader("📋 歷史判斷紀錄")
filtered = df[df["商品"].isin(selected_tickers)].sort_values("日期", ascending=False)
st.dataframe(filtered, width='stretch', hide_index=True)

st.caption("💡 想看報酬率追蹤圖表，請至左側選單切換到「報酬率追蹤」分頁")

"""
模擬交易儀表板 — 主頁面
------------------------------
- 卡片改為緊貼文字大小的排列，不再有多餘留白
- 持倉優先顯示；空手一律收進「更多」；若整個分類都空手，
  分類標題本身就是可點開的收合區塊
- 點擊卡片下方按鈕，K線圖直接展開在該列下方，可切換時間範圍
- 側邊欄篩選預設收合

執行方式：
    streamlit run dashboard.py
"""

import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
import streamlit as st

from common import inject_base_css, load_log, sidebar_filter, PERIOD_OPTIONS

st.set_page_config(page_title="量化交易模擬儀表板", layout="wide")
inject_base_css()
st.title("📈 模擬交易儀表板")

df = load_log()
if df is None:
    st.warning("還沒有任何紀錄，請先執行 python paper_trading_daily.py 產生資料")
    st.stop()


def classify(ticker):
    return "加密貨幣" if str(ticker).endswith("-USD") else "股票"


df["類型"] = df["商品"].apply(classify)
all_tickers = df["商品"].unique().tolist()
selected_tickers = sidebar_filter(all_tickers)

if "selected_chart_ticker" not in st.session_state:
    st.session_state.selected_chart_ticker = None


def render_candlestick(ticker):
    st.markdown(f"##### 🕯️ {ticker} K線圖")
    period_key = f"period_choice_{ticker}"
    if period_key not in st.session_state:
        st.session_state[period_key] = "本月"
    selected_period = st.radio(
        "時間範圍", list(PERIOD_OPTIONS.keys()),
        index=list(PERIOD_OPTIONS.keys()).index(st.session_state[period_key]),
        horizontal=True, key=f"radio_{ticker}",
    )
    st.session_state[period_key] = selected_period
    period, interval = PERIOD_OPTIONS[selected_period]

    with st.spinner("抓取資料中..."):
        try:
            data = yf.download(ticker, period=period, interval=interval, auto_adjust=True, progress=False)
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            data = data.reset_index()
            date_col = data.columns[0]
            n = len(data)
            x_vals = list(range(n))

            fig = go.Figure(data=[go.Candlestick(
                x=x_vals, open=data["Open"], high=data["High"],
                low=data["Low"], close=data["Close"],
            )])

            # 用K棒序號當X軸（而不是真實日期），保證每根K棒永遠等距排列，
            # 不會因為跳過週末/非交易時段而產生縫隙或刻度跑版
            date_format = "%m/%d %H:%M" if interval in ("5m", "15m") else "%Y-%m-%d"
            tick_count = min(8, n)
            tick_idx = sorted(set(int(i) for i in np.linspace(0, n - 1, tick_count)))
            tick_labels = [pd.to_datetime(data[date_col].iloc[i]).strftime(date_format) for i in tick_idx]
            fig.update_xaxes(tickmode="array", tickvals=tick_idx, ticktext=tick_labels)

            fig.update_layout(xaxis_rangeslider_visible=False, height=380,
                               margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, width='stretch')
            st.caption("💡 資料為點擊當下向 Yahoo Finance 即時抓取的最新報價，"
                        "不是連續推送的串流；「今日」使用5分鐘K棒，接近即時但非逐秒更新。")
        except Exception as e:
            st.error(f"抓取失敗: {e}")

    if st.button("關閉K線圖", key=f"close_{ticker}"):
        st.session_state.selected_chart_ticker = None
        st.rerun()
    st.markdown("---")


def render_card(ticker):
    latest_row = df[df["商品"] == ticker].sort_values("日期").iloc[-1]
    holding = latest_row["持倉狀態"] == "持倉中"
    if holding:
        style = "border:2px solid #2ecc71;background-color:rgba(46,204,113,0.10);"
        status = '<span style="color:#2ecc71;font-weight:bold;font-size:0.78em;">持倉中</span>'
        dot = "🟢 "
    else:
        style = "border:1px solid #444;"
        status = '<span style="color:#888;font-size:0.78em;">空手</span>'
        dot = ""

    st.markdown(
        f"""<div style="{style}border-radius:10px;padding:8px 14px;width:fit-content;
        min-width:130px;margin-bottom:4px;">
        <b style="font-size:0.95em;">{dot}{ticker}</b><br>
        <span style="font-size:1.0em;">${latest_row['收盤價']:,.2f}</span><br>
        {status}
        </div>""",
        unsafe_allow_html=True,
    )
    is_selected = st.session_state.selected_chart_ticker == ticker
    label = "🔽 收起K線圖" if is_selected else "📊 K線圖"
    if st.button(label, key=f"chart_btn_{ticker}"):
        st.session_state.selected_chart_ticker = None if is_selected else ticker
        st.rerun()


def render_grid(ticker_list, max_cols=8):
    for i in range(0, len(ticker_list), max_cols):
        row_tickers = ticker_list[i:i + max_cols]
        cols = st.columns(max_cols)
        for col, ticker in zip(cols, row_tickers):
            with col:
                render_card(ticker)
        if st.session_state.selected_chart_ticker in row_tickers:
            render_candlestick(st.session_state.selected_chart_ticker)


def render_group(title, emoji, group_tickers):
    if not group_tickers:
        return
    latest_by_ticker = {t: df[df["商品"] == t].sort_values("日期").iloc[-1] for t in group_tickers}
    holding_list = [t for t in group_tickers if latest_by_ticker[t]["持倉狀態"] == "持倉中"]
    watching_list = [t for t in group_tickers if t not in holding_list]

    if holding_list:
        st.markdown(f"#### {emoji} {title}")
        render_grid(holding_list)
        if watching_list:
            with st.expander(f"更多（空手觀望 {len(watching_list)} 檔）"):
                render_grid(watching_list)
    else:
        with st.expander(f"{emoji} {title}（目前無持倉，{len(watching_list)} 檔觀望中，點開查看）"):
            render_grid(watching_list)
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

st.divider()
st.caption("💡 完整歷史紀錄請至左側選單「歷史紀錄」分頁；報酬率追蹤圖表請至「報酬率追蹤」分頁")

"""
模擬交易儀表板 — 主頁面（清單式排版 + 搜尋/排序）
------------------------------------------------------
- 整行依漲跌染色（紅跌綠漲）
- 今日熱門股下方可搜尋代號
- 支援排序：持倉優先 / 現價高到低 / 現價低到高 / 漲幅最大 / 跌幅最大 / 代號A-Z
- 全部攤開顯示，不再收合

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

only_holding = st.sidebar.checkbox("只顯示持倉", value=False)

if "selected_chart_ticker" not in st.session_state:
    st.session_state.selected_chart_ticker = None
if "pinned_tickers" not in st.session_state:
    st.session_state.pinned_tickers = set()
if "sort_column" not in st.session_state:
    st.session_state.sort_column = "商品"
if "sort_ascending" not in st.session_state:
    st.session_state.sort_ascending = True


def get_ticker_info(ticker):
    history = df[df["商品"] == ticker].sort_values("日期")
    latest_row = history.iloc[-1]
    price = latest_row["收盤價"]
    holding = latest_row["持倉狀態"] == "持倉中"
    if len(history) >= 2:
        prev_price = history["收盤價"].iloc[-2]
        pct_change = (price / prev_price - 1) if prev_price else None
    else:
        pct_change = None
    spark_prices = history["收盤價"].tail(15).tolist()
    return {"price": price, "holding": holding, "pct_change": pct_change, "spark_prices": spark_prices}


def sort_tickers(ticker_list, mode=None):
    info = {t: get_ticker_info(t) for t in ticker_list}
    col = st.session_state.sort_column
    asc = st.session_state.sort_ascending

    def key(t):
        if col == "商品":
            return t
        if col == "現價":
            return info[t]["price"]
        if col == "漲跌":
            return info[t]["pct_change"] if info[t]["pct_change"] is not None else -999
        if col == "狀態":
            return 0 if info[t]["holding"] else 1
        return t

    pinned = [t for t in ticker_list if t in st.session_state.pinned_tickers]
    unpinned = [t for t in ticker_list if t not in st.session_state.pinned_tickers]
    return sorted(pinned, key=key, reverse=not asc) + sorted(unpinned, key=key, reverse=not asc)


def make_sparkline_svg(prices, width=90, height=28, color="#2ecc71"):
    if len(prices) < 2:
        return f'<svg width="{width}" height="{height}"></svg>'
    min_p, max_p = min(prices), max(prices)
    range_p = (max_p - min_p) or 1
    step = width / (len(prices) - 1)
    points = " ".join(
        f"{i * step:.1f},{height - 2 - ((p - min_p) / range_p) * (height - 4):.1f}"
        for i, p in enumerate(prices)
    )
    return (f'<svg width="{width}" height="{height}">'
            f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="1.6"/></svg>')


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


SORTABLE_COLUMNS = ["商品", "現價", "漲跌", "狀態"]


def render_header():
    cols = st.columns([1.4, 1.2, 1.2, 1.3, 0.9, 0.5, 1])
    labels = ["商品", "現價", "漲跌", "走勢", "狀態"]
    for col, label in zip(cols[:5], labels):
        with col:
            if label in SORTABLE_COLUMNS:
                is_active = st.session_state.sort_column == label
                arrow = ("▲" if st.session_state.sort_ascending else "▼") if is_active else ""
                if st.button(f"{label} {arrow}", key=f"sort_header_{label}"):
                    if is_active:
                        st.session_state.sort_ascending = not st.session_state.sort_ascending
                    else:
                        st.session_state.sort_column = label
                        st.session_state.sort_ascending = True
                    st.rerun()
            else:
                st.markdown(f"<span style='color:#888;font-size:0.8em;'>{label}</span>", unsafe_allow_html=True)
    with cols[5]:
        st.markdown("<span style='color:#888;font-size:0.8em;'>釘選</span>", unsafe_allow_html=True)
    with cols[6]:
        st.markdown("<span style='color:#888;font-size:0.8em;'>操作</span>", unsafe_allow_html=True)


def render_row(ticker):
    info = get_ticker_info(ticker)
    price, holding, pct_change, spark_prices = info["price"], info["holding"], info["pct_change"], info["spark_prices"]

    if pct_change is None:
        bg_color = "rgba(255,255,255,0.03)"
        change_color = "#888"
        arrow = "—"
        change_text = "—"
        spark_color = "#888"
    elif pct_change >= 0:
        bg_color = "rgba(46,204,113,0.12)"
        change_color = "#2ecc71"
        arrow = "▲"
        change_text = f"{pct_change:+.2%}"
        spark_color = "#2ecc71"
    else:
        bg_color = "rgba(231,76,60,0.12)"
        change_color = "#e74c3c"
        arrow = "▼"
        change_text = f"{pct_change:+.2%}"
        spark_color = "#e74c3c"

    spark_svg = make_sparkline_svg(spark_prices, color=spark_color)
    status_html = ('<span style="color:#2ecc71;">🟢 持倉</span>' if holding
                    else '<span style="color:#888;">⚪ 空手</span>')

    row_html = f"""
    <div style="display:flex;align-items:center;background-color:{bg_color};
    border-radius:6px;padding:8px 12px;">
        <div style="flex:1.4;font-weight:700;">{ticker}</div>
        <div style="flex:1.2;">${price:,.2f}</div>
        <div style="flex:1.2;color:{change_color};font-weight:600;">{arrow} {change_text}</div>
        <div style="flex:1.3;">{spark_svg}</div>
        <div style="flex:0.9;">{status_html}</div>
    </div>
    """

    cols = st.columns([5, 0.5, 1])
    with cols[0]:
        st.markdown(row_html, unsafe_allow_html=True)
    with cols[1]:
        is_pinned = ticker in st.session_state.pinned_tickers
        if st.button("★" if is_pinned else "☆", key=f"pin_{ticker}"):
            if is_pinned:
                st.session_state.pinned_tickers.discard(ticker)
            else:
                st.session_state.pinned_tickers.add(ticker)
            st.rerun()
    with cols[2]:
        is_selected = st.session_state.selected_chart_ticker == ticker
        label = "收起" if is_selected else "K線圖"
        if st.button(label, key=f"chart_btn_{ticker}"):
            st.session_state.selected_chart_ticker = None if is_selected else ticker
            st.rerun()

    if st.session_state.selected_chart_ticker == ticker:
        render_candlestick(ticker)


def render_list(ticker_list):
    ticker_list = sort_tickers(ticker_list)
    render_header()
    for ticker in ticker_list:
        render_row(ticker)


st.subheader("今日最新狀態")

watchlist_tickers = df[df["來源"] == "追蹤清單"]["商品"].unique().tolist()
hot_tickers = df[df["來源"] == "今日熱門"]["商品"].unique().tolist()
moomoo_tickers = df[df["來源"] == "moomoo清單"]["商品"].unique().tolist() if "moomoo清單" in df["來源"].unique() else []

crypto_tickers = [t for t in selected_tickers if t in watchlist_tickers and classify(t) == "加密貨幣"]
stock_tickers = [t for t in selected_tickers if t in watchlist_tickers and classify(t) == "股票"]
hot_selected = [t for t in selected_tickers if t in hot_tickers]
moomoo_selected = [t for t in selected_tickers if t in moomoo_tickers]

if only_holding:
    crypto_tickers = [t for t in crypto_tickers if get_ticker_info(t)["holding"]]
    stock_tickers = [t for t in stock_tickers if get_ticker_info(t)["holding"]]
    hot_selected = [t for t in hot_selected if get_ticker_info(t)["holding"]]
    moomoo_selected = [t for t in moomoo_selected if get_ticker_info(t)["holding"]]

# ---------- 總覽列 ----------
all_shown = crypto_tickers + stock_tickers + hot_selected + moomoo_selected
if all_shown:
    infos = {t: get_ticker_info(t) for t in all_shown}
    holding_count = sum(1 for i in infos.values() if i["holding"])
    up_count = sum(1 for i in infos.values() if i["pct_change"] is not None and i["pct_change"] > 0)
    down_count = sum(1 for i in infos.values() if i["pct_change"] is not None and i["pct_change"] < 0)

    ov1, ov2, ov3, ov4 = st.columns(4)
    ov1.metric("追蹤商品數", len(all_shown))
    ov2.metric("持倉中", holding_count)
    ov3.metric("📈 上漲", up_count)
    ov4.metric("📉 下跌", down_count)
    st.markdown("")

if crypto_tickers:
    st.markdown("#### 🪙 加密貨幣")
    render_list(crypto_tickers)
    st.markdown("")

if stock_tickers:
    st.markdown("#### 📊 股票（追蹤清單）")
    render_list(stock_tickers)
    st.markdown("")

if moomoo_selected:
    st.markdown("#### 🐮 moomoo 追蹤清單")
    render_list(moomoo_selected)
    st.markdown("")

st.markdown("#### 🔥 今日熱門股（Yahoo Most Active）")
search_query = st.text_input("🔍 搜尋股票代號", placeholder="輸入代號，例如 AAPL", key="hot_search")
filtered_hot = [t for t in hot_selected if search_query.upper() in t.upper()] if search_query else hot_selected
if filtered_hot:
    render_list(filtered_hot)
else:
    st.info("找不到符合的商品" if search_query else "目前沒有今日熱門股資料")

st.divider()
st.caption("💡 完整歷史紀錄請至左側選單「歷史紀錄」分頁；報酬率追蹤圖表請至「報酬率追蹤」分頁")

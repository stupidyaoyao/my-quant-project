"""
應用程式進入點（單一檔案版本，避免跨檔案動態載入造成的排版問題）
------------------------------------------------------
所有分頁邏輯直接合併在這個檔案裡，不再用 importlib 動態載入其他檔案，
避免 Streamlit 對「畫面元素該畫在哪裡」的追蹤跟動態載入的模組衝突。

頂層三大分類：均線策略模擬 / ORB當沖模擬 / moomoo實際帳戶
每個分類底下有各自的子分頁。

執行方式：
    streamlit run app.py
"""

import json
import os
from datetime import datetime, timezone

import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
import streamlit as st

from common import inject_base_css, load_log, sidebar_filter, PERIOD_OPTIONS

_df = None


# ---------- 均線策略模擬：總覽 ----------
def classify(ticker):
    return "加密貨幣" if str(ticker).endswith("-USD") else "股票"


def get_ticker_info(ticker):
    history = _df[_df["商品"] == ticker].sort_values("日期")
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


def sort_tickers(ticker_list):
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


def make_sparkline_svg(prices, width=90, height=28, color="#2fbf6a"):
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
    st.markdown(f"##### {ticker} 走勢圖")
    period_key = f"period_choice_{ticker}"
    if period_key not in st.session_state:
        st.session_state[period_key] = "本月"

    period_labels = list(PERIOD_OPTIONS.keys())
    tab_cols = st.columns(len(period_labels))
    for col, label in zip(tab_cols, period_labels):
        with col:
            is_active = st.session_state[period_key] == label
            display = f"● {label}" if is_active else label
            if st.button(display, key=f"period_btn_{ticker}_{label}"):
                st.session_state[period_key] = label
                st.rerun()

    selected_period = st.session_state[period_key]
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
            closes = data["Close"]

            is_up = closes.iloc[-1] >= closes.iloc[0]
            line_color = "#2fbf6a" if is_up else "#e34a3a"
            fill_rgb = "47,191,106" if is_up else "227,74,58"

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=x_vals, y=closes, mode="lines",
                line=dict(color=line_color, width=2),
                fill="tozeroy",
                fillgradient=dict(
                    type="vertical",
                    colorscale=[[0, f"rgba({fill_rgb},0.35)"], [1, f"rgba({fill_rgb},0)"]],
                ),
                hoverinfo="skip",
            ))

            date_format = "%m/%d %H:%M" if interval in ("5m", "15m") else "%Y-%m-%d"
            tick_count = min(6, n)
            tick_idx = sorted(set(int(i) for i in np.linspace(0, n - 1, tick_count)))
            tick_labels = [pd.to_datetime(data[date_col].iloc[i]).strftime(date_format) for i in tick_idx]
            fig.update_xaxes(tickmode="array", tickvals=tick_idx, ticktext=tick_labels,
                              showgrid=False, zeroline=False)
            fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.06)", zeroline=False)
            fig.update_layout(
                showlegend=False, height=320,
                margin=dict(l=10, r=10, t=10, b=10),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, width='stretch')
            st.caption("💡 資料為點擊當下向 Yahoo Finance 即時抓取的最新報價，"
                        "不是連續推送的串流；「今日」使用5分鐘K棒，接近即時但非逐秒更新。")
        except Exception as e:
            st.error(f"抓取失敗: {e}")

    if st.button("關閉走勢圖", key=f"close_{ticker}"):
        st.session_state.selected_chart_ticker = None
        st.rerun()
    st.markdown("---")


SORTABLE_COLUMNS = ["商品", "現價", "漲跌", "狀態"]


def render_header(group_key):
    cols = st.columns([1.4, 1.2, 1.2, 1.3, 0.9, 0.5, 1])
    labels = ["商品", "現價", "漲跌", "走勢", "狀態"]
    for col, label in zip(cols[:5], labels):
        with col:
            if label in SORTABLE_COLUMNS:
                is_active = st.session_state.sort_column == label
                arrow = ("▲" if st.session_state.sort_ascending else "▼") if is_active else ""
                if st.button(f"{label} {arrow}", key=f"sort_header_{group_key}_{label}", type="tertiary"):
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
        bg_style = "linear-gradient(90deg, rgba(255,255,255,0.015) 0%, rgba(255,255,255,0.05) 100%)"
        change_color, arrow, change_text, spark_color = "#888", "—", "—", "#888"
    elif pct_change >= 0:
        bg_style = "linear-gradient(90deg, rgba(47,191,106,0.03) 0%, rgba(47,191,106,0.20) 100%)"
        change_color, arrow, change_text, spark_color = "#2fbf6a", "▲", f"{pct_change:+.2%}", "#2fbf6a"
    else:
        bg_style = "linear-gradient(90deg, rgba(227,74,58,0.03) 0%, rgba(227,74,58,0.20) 100%)"
        change_color, arrow, change_text, spark_color = "#e34a3a", "▼", f"{pct_change:+.2%}", "#e34a3a"

    spark_svg = make_sparkline_svg(spark_prices, color=spark_color)
    status_html = (
        '<span style="background:rgba(47,191,106,0.25);color:#2fbf6a;padding:2px 10px;'
        'border-radius:10px;font-size:0.85em;">持倉中</span>' if holding
        else '<span style="background:rgba(255,255,255,0.08);color:#888;padding:2px 10px;'
        'border-radius:10px;font-size:0.85em;">空手</span>'
    )

    row_html = f"""
    <div style="display:flex;align-items:center;background:{bg_style};
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
        label = "收起" if is_selected else "走勢圖"
        if st.button(label, key=f"chart_btn_{ticker}"):
            st.session_state.selected_chart_ticker = None if is_selected else ticker
            st.rerun()

    if st.session_state.selected_chart_ticker == ticker:
        render_candlestick(ticker)


def render_list(ticker_list, group_key, show_header=False):
    ticker_list = sort_tickers(ticker_list)
    if show_header:
        render_header(group_key)
    for ticker in ticker_list:
        render_row(ticker)


def render_overview():
    global _df
    st.title("均線策略模擬 — 總覽")

    _df = load_log()
    if _df is None:
        st.warning("還沒有任何紀錄，請先執行 python paper_trading_daily.py 產生資料")
        return

    _df["類型"] = _df["商品"].apply(classify)
    all_tickers = _df["商品"].unique().tolist()

    if "selected_chart_ticker" not in st.session_state:
        st.session_state.selected_chart_ticker = None
    if "pinned_tickers" not in st.session_state:
        st.session_state.pinned_tickers = set()
    if "sort_column" not in st.session_state:
        st.session_state.sort_column = "商品"
    if "sort_ascending" not in st.session_state:
        st.session_state.sort_ascending = True

    watchlist_tickers = _df[_df["來源"] == "追蹤清單"]["商品"].unique().tolist()
    hot_tickers = _df[_df["來源"] == "今日熱門"]["商品"].unique().tolist()
    moomoo_tickers = _df[_df["來源"] == "moomoo清單"]["商品"].unique().tolist() if "moomoo清單" in _df["來源"].unique() else []

    # ---------- 統計卡片：反映全部追蹤商品，不受下方搜尋框影響 ----------
    all_shown = [t for t in all_tickers if t in watchlist_tickers or t in hot_tickers or t in moomoo_tickers]
    if all_shown:
        infos = {t: get_ticker_info(t) for t in all_shown}
        holding_count = sum(1 for i in infos.values() if i["holding"])
        up_count = sum(1 for i in infos.values() if i["pct_change"] is not None and i["pct_change"] > 0)
        down_count = sum(1 for i in infos.values() if i["pct_change"] is not None and i["pct_change"] < 0)

        stat_cols = st.columns(4)
        stat_defs = [
            ("追蹤商品數", len(all_shown), ""),
            ("持倉中", holding_count, ""),
            ("今日上漲", up_count, "up"),
            ("今日下跌", down_count, "down"),
        ]
        for col, (label, value, variant) in zip(stat_cols, stat_defs):
            value_class = f"stat-value {variant}-text" if variant else "stat-value"
            with col:
                st.markdown(
                    f"""<div class="stat-card {variant}">
                    <div class="stat-label">{label}</div>
                    <div class="{value_class}">{value}</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
        st.markdown("")

    # ---------- 搜尋/篩選：只影響下方商品清單 ----------
    search_col, holding_col, filter_col = st.columns([3, 1.2, 1])
    with search_col:
        global_search = st.text_input("搜尋商品代號或名稱", placeholder="搜尋商品代號或名稱",
                                        key="overview_search", label_visibility="collapsed")
    with holding_col:
        only_holding = st.checkbox("只顯示持倉", value=False, key="overview_only_holding")
    with filter_col:
        with st.popover("篩選 ▾", width='stretch'):
            selected_tickers = st.multiselect("選擇要顯示的商品", all_tickers, default=all_tickers, key="overview_multiselect")

    if global_search:
        selected_tickers = [t for t in selected_tickers if global_search.upper() in t.upper()]

    crypto_tickers = [t for t in selected_tickers if t in watchlist_tickers and classify(t) == "加密貨幣"]
    stock_tickers = [t for t in selected_tickers if t in watchlist_tickers and classify(t) == "股票"]
    hot_selected = [t for t in selected_tickers if t in hot_tickers]
    moomoo_selected = [t for t in selected_tickers if t in moomoo_tickers]

    if only_holding:
        crypto_tickers = [t for t in crypto_tickers if get_ticker_info(t)["holding"]]
        stock_tickers = [t for t in stock_tickers if get_ticker_info(t)["holding"]]
        hot_selected = [t for t in hot_selected if get_ticker_info(t)["holding"]]
        moomoo_selected = [t for t in moomoo_selected if get_ticker_info(t)["holding"]]

    header_shown = {"done": False}

    def render_group_section(title, ticker_list, group_key):
        if not ticker_list:
            return
        expand_key = f"group_expanded_{group_key}"
        if expand_key not in st.session_state:
            st.session_state[expand_key] = True
        arrow = "▾" if st.session_state[expand_key] else "▸"
        with st.container(key=f"grouptoggle_container_{group_key}"):
            if st.button(f"{arrow}  {title} ({len(ticker_list)})", key=f"grouptoggle_{group_key}", type="tertiary"):
                st.session_state[expand_key] = not st.session_state[expand_key]
                st.rerun()
        if st.session_state[expand_key]:
            show_header = not header_shown["done"]
            render_list(ticker_list, group_key, show_header=show_header)
            header_shown["done"] = True
        st.markdown("")

    render_group_section("加密貨幣", crypto_tickers, "crypto")
    render_group_section("股票（追蹤清單）", stock_tickers, "stock")
    render_group_section("moomoo 追蹤清單", moomoo_selected, "moomoo")
    render_group_section("今日熱門股（Yahoo Most Active）", hot_selected, "hot")

# ---------- 均線策略模擬：新聞 ----------
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

# ---------- 均線策略模擬：報酬率追蹤 ----------
def render_returns():
    st.title("報酬率追蹤")

    df = load_log()
    if df is None:
        st.warning("還沒有任何紀錄，請先執行 python paper_trading_daily.py 產生資料")
        return
    if "浮動報酬" not in df.columns:
        st.info("目前使用的是舊版紀錄檔，還沒有報酬率資料")
        return

    df["浮動報酬"] = pd.to_numeric(df["浮動報酬"], errors="coerce")
    tickers = df["商品"].unique().tolist()
    selected_tickers = sidebar_filter(tickers, key="returns")
    filtered = df[df["商品"].isin(selected_tickers)].sort_values("日期")

    if not filtered["浮動報酬"].notna().any():
        st.info("目前還沒有持倉紀錄可以追蹤報酬率")
        return

    return_tickers = [t for t in selected_tickers if filtered[filtered["商品"] == t]["浮動報酬"].notna().any()]
    for ticker in return_tickers:
        t_df = filtered[(filtered["商品"] == ticker) & (filtered["浮動報酬"].notna())]
        if len(t_df) >= 1:
            series = t_df.set_index("日期")["浮動報酬"] * 100
            st.line_chart(series, height=220, width='stretch')
            latest_return = series.iloc[-1]
            arrow = "▲" if latest_return >= 0 else "▼"
            st.caption(f"{ticker} 浮動報酬率 (%) — 目前 {arrow} {latest_return:.2f}%")
            st.divider()

# ---------- 歷史紀錄（均線+ORB共用）----------
def normalize_ma_log(df):
    df = df.copy()
    df["建議"] = df["建議"].fillna("")
    mask = df["建議"].str.startswith("買進訊號") | df["建議"].str.startswith("賣出訊號")
    df = df[mask].copy()
    if df.empty:
        return pd.DataFrame(columns=["日期", "時間", "商品", "策略", "訊號", "價格", "結果"])

    def get_signal(row):
        if row["建議"].startswith("買進訊號"):
            return "進場"
        elif "ATR停損" in row["建議"]:
            return "停損出場"
        return "訊號出場"

    def get_result(row):
        if row["建議"].startswith("買進訊號"):
            return "持有中"
        try:
            ret = float(row.get("浮動報酬"))
            return "獲利" if ret > 0 else "虧損"
        except (TypeError, ValueError):
            return "-"

    return pd.DataFrame({
        "日期": pd.to_datetime(df["日期"]), "時間": "", "商品": df["商品"], "策略": "均線策略",
        "訊號": df.apply(get_signal, axis=1),
        "價格": pd.to_numeric(df["收盤價"], errors="coerce"),
        "結果": df.apply(get_result, axis=1),
    })


def normalize_orb_log(df):
    df = df.copy()
    dt = pd.to_datetime(df["時間"])

    def get_signal(row):
        event = row["事件"]
        if event == "進場":
            return "進場"
        elif "停損" in event:
            return "停損出場"
        elif "停利" in event:
            return "停利出場"
        return event

    def get_result(row):
        if row["事件"] == "進場":
            return "持有中"
        try:
            r = float(row.get("R值"))
            return "獲利" if r > 0 else "虧損"
        except (TypeError, ValueError):
            return "-"

    return pd.DataFrame({
        "日期": dt.dt.normalize(), "時間": dt.dt.strftime("%H:%M"), "商品": df["商品"], "策略": "ORB當沖",
        "訊號": df.apply(get_signal, axis=1),
        "價格": pd.to_numeric(df["價格"], errors="coerce"),
        "結果": df.apply(get_result, axis=1),
    })


def color_result(val):
    if val == "獲利":
        return "color: #2fbf6a; font-weight: 600;"
    elif val == "虧損":
        return "color: #e34a3a; font-weight: 600;"
    return ""


def color_signal(val):
    if val == "進場":
        return "color: #6366f1; font-weight: 600;"
    elif "停損" in str(val):
        return "color: #e34a3a;"
    elif "停利" in str(val) or val == "訊號出場":
        return "color: #2fbf6a;"
    return ""


def render_history(default_strategy="全部"):
    st.title("歷史紀錄")

    frames = []
    if os.path.exists("paper_trading_log.csv"):
        ma_df = pd.read_csv("paper_trading_log.csv", encoding="utf-8-sig")
        frames.append(normalize_ma_log(ma_df))
    if os.path.exists("orb_log.csv"):
        orb_df = pd.read_csv("orb_log.csv", encoding="utf-8-sig")
        if not orb_df.empty:
            frames.append(normalize_orb_log(orb_df))

    if not frames or all(f.empty for f in frames):
        st.warning("還沒有任何紀錄")
        return

    combined = pd.concat(frames, ignore_index=True).sort_values(["日期", "時間"], ascending=[False, False])

    date_filter = st.radio("時間範圍", ["今日", "本周", "本月", "今年", "全部"], horizontal=True, index=4)
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

    col1, col2 = st.columns([2, 3])
    with col1:
        options = ["全部", "均線策略", "ORB當沖"]
        strategy_filter = st.radio("策略", options, horizontal=True, index=options.index(default_strategy))
    with col2:
        search = st.text_input("搜尋商品代號或名稱", placeholder="輸入代號，例如 AAPL")

    filtered = combined.copy()
    if start_date is not None:
        filtered = filtered[filtered["日期"] >= start_date]
    if strategy_filter != "全部":
        filtered = filtered[filtered["策略"] == strategy_filter]
    if search:
        filtered = filtered[filtered["商品"].str.upper().str.contains(search.upper())]

    st.caption(f"共 {len(filtered)} 筆紀錄")
    display_df = filtered.copy()
    display_df["日期"] = display_df["日期"].dt.strftime("%Y-%m-%d")
    styled = display_df.style.map(color_result, subset=["結果"]).map(color_signal, subset=["訊號"])
    st.dataframe(styled, width='stretch', hide_index=True)

# ---------- ORB當沖模擬：盤前掃描 ----------
def render_premarket():
    st.title("盤前爆量股掃描")

    DATA_FILE = "premarket_gappers.json"
    if not os.path.exists(DATA_FILE):
        st.warning("還沒有掃描資料，請先執行 python premarket_scanner.py 產生資料")
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    st.caption(f"掃描時間：{data.get('scanned_at', '未知時間')}")
    gappers = data.get("gappers", [])
    if not gappers:
        st.info("目前沒有符合條件的盤前爆量股（漲幅>5%、股價>$3、盤前成交量>5萬股）")
        return

    for g in gappers:
        is_premarket = g.get("is_premarket_data", True)
        data_tag = "" if is_premarket else "（非盤前時段，以當日漲跌幅估算）"
        col1, col2 = st.columns([1, 4])
        with col1:
            st.markdown(
                f"""<div style="border:2px solid #2fbf6a;border-radius:10px;padding:12px;
                background-color:rgba(47,191,106,0.10);text-align:center;">
                <div style="font-size:0.85em;color:#888;">#{g['rank']}</div>
                <b style="font-size:1.2em;">{g['symbol']}</b><br>
                <span style="font-size:1.1em;">${g['price']:,.2f}</span><br>
                <span style="color:#2fbf6a;font-weight:bold;">+{g['gap_pct']:.2f}%</span>
                </div>""",
                unsafe_allow_html=True,
            )
        with col2:
            st.markdown(f"**盤前成交量**：{g['premarket_volume']:,}{data_tag}")
            st.markdown(f"**上漲原因**：{g.get('catalyst') or '無相關新聞'}")
            for headline in g.get("headlines", [])[1:]:
                st.caption(headline)
        st.divider()

# ---------- ORB當沖模擬：ORB當沖監控 ----------
def render_orb():
    st.title("ORB 當沖監控")
    st.caption("策略：30分鐘回測確認型，停利2R，動態watchlist（盤前掃描+今日熱門+ATR篩選）")

    LOG_FILE = "orb_log.csv"
    if not os.path.exists(LOG_FILE):
        st.warning("還沒有任何紀錄，排程會在美股開盤時段自動產生資料")
        return

    df = pd.read_csv(LOG_FILE, encoding="utf-8-sig")
    if df.empty:
        st.info("還沒有任何事件紀錄")
        return

    df["時間"] = pd.to_datetime(df["時間"])
    df = df.sort_values("時間", ascending=False)

    today = pd.Timestamp.now().normalize()
    today_events = df[df["時間"] >= today]
    entries_today = today_events[today_events["事件"] == "進場"]
    exits_today = today_events[today_events["事件"].str.startswith("出場", na=False)]

    col1, col2, col3 = st.columns(3)
    col1.metric("今日進場次數", len(entries_today))
    col2.metric("今日出場次數", len(exits_today))
    if not exits_today.empty and "R值" in exits_today.columns:
        wins = exits_today[pd.to_numeric(exits_today["R值"], errors="coerce") > 0]
        win_rate = len(wins) / len(exits_today) if len(exits_today) > 0 else 0
        col3.metric("今日勝率", f"{win_rate:.0%}")
    else:
        col3.metric("今日勝率", "—")

    st.divider()
    st.subheader("事件紀錄")

    tickers = df["商品"].unique().tolist()
    selected = st.multiselect("篩選商品", tickers, default=tickers)
    filtered = df[df["商品"].isin(selected)]

    for _, row in filtered.iterrows():
        event = row["事件"]
        is_entry = event == "進場"
        r_val = None
        if pd.notna(row.get("R值")) and str(row.get("R值")) != "":
            try:
                r_val = float(row["R值"])
            except (ValueError, TypeError):
                pass

        if is_entry:
            bg, tag_color, tag = "linear-gradient(90deg, rgba(99,102,241,0.03) 0%, rgba(99,102,241,0.18) 100%)", "#6366f1", "進場"
        elif r_val is not None and r_val > 0:
            bg, tag_color, tag = "linear-gradient(90deg, rgba(47,191,106,0.03) 0%, rgba(47,191,106,0.18) 100%)", "#2fbf6a", event
        elif r_val is not None:
            bg, tag_color, tag = "linear-gradient(90deg, rgba(227,74,58,0.03) 0%, rgba(227,74,58,0.18) 100%)", "#e34a3a", event
        else:
            bg, tag_color, tag = "linear-gradient(90deg, rgba(255,255,255,0.015) 0%, rgba(255,255,255,0.05) 100%)", "#888", event

        r_display = f"<span style='color:{tag_color};font-weight:700;'>{r_val:+.1f}R</span>" if r_val is not None else ""

        st.markdown(
            f"""<div style="display:flex;align-items:center;background:{bg};
            border-radius:6px;padding:10px 14px;margin-bottom:6px;">
            <div style="flex:1.3;font-weight:700;">{row['商品']}</div>
            <div style="flex:1;color:{tag_color};font-weight:600;">{tag}</div>
            <div style="flex:1.3;">${row['價格']:,.2f}</div>
            <div style="flex:1;">{r_display}</div>
            <div style="flex:1.8;color:#888;font-size:0.85em;">{row['備註']}</div>
            <div style="flex:1.3;color:#888;font-size:0.8em;text-align:right;">{row['時間'].strftime('%m/%d %H:%M')}</div>
            </div>""",
            unsafe_allow_html=True,
        )

# ---------- moomoo實際帳戶：帳戶持倉 ----------
def render_moomoo_position_row(p):
    pl = p.get("pl", 0)
    pl_ratio = p.get("pl_ratio", 0)
    bg = "rgba(47,191,106,0.12)" if pl >= 0 else "rgba(227,74,58,0.12)"
    color = "#2fbf6a" if pl >= 0 else "#e34a3a"
    st.markdown(
        f"""<div style="display:flex;align-items:center;background:{bg};
        border-radius:6px;padding:10px 14px;margin-bottom:6px;">
        <div style="flex:1.3;font-weight:700;">{p['code']}</div>
        <div style="flex:1.5;color:#888;">{p.get('name', '')}</div>
        <div style="flex:1;">{p['qty']:.0f} 股</div>
        <div style="flex:1.2;">成本 ${p['cost_price']:,.2f}</div>
        <div style="flex:1.2;">現價 ${p['current_price']:,.2f}</div>
        <div style="flex:1.3;color:{color};font-weight:600;">${pl:,.2f}（{pl_ratio:+.2f}%）</div>
        </div>""",
        unsafe_allow_html=True,
    )


def render_moomoo():
    st.title("moomoo 帳戶持倉")

    DATA_FILE = "moomoo_positions.json"
    if not os.path.exists(DATA_FILE):
        st.warning("還沒有同步過資料，請在本機執行 python sync_moomoo_positions.py 產生資料")
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    st.caption(f"上次同步時間：{data.get('synced_at', '未知')}（非即時，需在本機OpenD開著時手動同步更新）")

    # ---------- 真實帳戶：明顯警示視覺，放在最上面 ----------
    real = data.get("real")
    st.markdown(
        """<div style="border:2px solid #e34a3a;border-radius:10px;padding:14px 18px;
        background:linear-gradient(135deg, rgba(227,74,58,0.15) 0%, rgba(227,74,58,0.04) 100%);
        margin-bottom:16px;">
        <b style="color:#e34a3a;font-size:1.1em;">⚠️ 真實帳戶（真錢，僅讀取顯示，系統不會對此帳戶下單）</b>
        </div>""",
        unsafe_allow_html=True,
    )
    if real is None:
        st.info("真實帳戶：沒有讀到資料")
    else:
        col1, col2 = st.columns(2)
        col1.metric("淨資產", f"${real.get('net_assets', 0):,.2f}")
        col2.metric("持倉數量", len(real.get("positions", [])))
        positions = real.get("positions", [])
        if not positions:
            st.info("目前沒有任何持倉")
        else:
            for p in positions:
                render_moomoo_position_row(p)

    st.divider()

    # ---------- 模擬帳戶：中性視覺 ----------
    st.markdown(
        """<div style="border:1px solid #444;border-radius:10px;padding:10px 18px;margin-bottom:16px;">
        <b>模擬帳戶（模擬盤・虛擬資金，非真錢）</b>
        </div>""",
        unsafe_allow_html=True,
    )
    sim = data.get("simulate")
    if sim is None:
        st.info("模擬帳戶：沒有讀到資料")
    else:
        col1, col2 = st.columns(2)
        col1.metric("淨資產", f"${sim.get('net_assets', 0):,.2f}")
        col2.metric("持倉數量", len(sim.get("positions", [])))
        positions = sim.get("positions", [])
        if not positions:
            st.info("目前沒有任何持倉")
        else:
            for p in positions:
                render_moomoo_position_row(p)


# ======================================================
# 路由器主邏輯
# ======================================================

st.set_page_config(page_title="量化交易模擬儀表板", layout="wide")
inject_base_css()

NAV_STRUCTURE = {
    "均線策略模擬": ["總覽", "新聞", "報酬率追蹤", "歷史紀錄"],
    "ORB當沖模擬": ["盤前掃描", "ORB當沖監控", "歷史紀錄"],
    "moomoo實際帳戶": ["帳戶持倉"],
}

if "nav_group" not in st.session_state:
    st.session_state.nav_group = "均線策略模擬"
if "nav_subpage" not in st.session_state:
    st.session_state.nav_subpage = "總覽"

group_names = list(NAV_STRUCTURE.keys())
with st.container(key="nav_group_row"):
    st.markdown('<div style="text-align:center;">', unsafe_allow_html=True)
    selected_group = st.radio("大分類", group_names, horizontal=True,
                                index=group_names.index(st.session_state.nav_group),
                                key="nav_group_radio", label_visibility="collapsed")
    st.markdown('</div>', unsafe_allow_html=True)

if selected_group != st.session_state.nav_group:
    st.session_state.nav_group = selected_group
    st.session_state.nav_subpage = NAV_STRUCTURE[selected_group][0]
    st.rerun()

current_subpages = NAV_STRUCTURE[st.session_state.nav_group]
with st.container(key="nav_subgroup_row"):
    st.markdown('<div style="text-align:center;">', unsafe_allow_html=True)
    selected_sub = st.radio("子分頁", current_subpages, horizontal=True,
                              index=current_subpages.index(st.session_state.nav_subpage),
                              key=f"nav_sub_radio_{st.session_state.nav_group}", label_visibility="collapsed")
    st.markdown('</div>', unsafe_allow_html=True)

if selected_sub != st.session_state.nav_subpage:
    st.session_state.nav_subpage = selected_sub
    st.rerun()

st.divider()

group = st.session_state.nav_group
sub = st.session_state.nav_subpage

if group == "均線策略模擬":
    if sub == "總覽":
        render_overview()
    elif sub == "新聞":
        render_news()
    elif sub == "報酬率追蹤":
        render_returns()
    elif sub == "歷史紀錄":
        render_history(default_strategy="均線策略")

elif group == "ORB當沖模擬":
    if sub == "盤前掃描":
        render_premarket()
    elif sub == "ORB當沖監控":
        render_orb()
    elif sub == "歷史紀錄":
        render_history(default_strategy="ORB當沖")

elif group == "moomoo實際帳戶":
    if sub == "帳戶持倉":
        render_moomoo()

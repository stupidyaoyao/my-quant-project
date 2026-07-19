"""報酬率追蹤（函式化版本，供 app.py 路由器呼叫）"""

import pandas as pd
import streamlit as st

from common import load_log, sidebar_filter


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

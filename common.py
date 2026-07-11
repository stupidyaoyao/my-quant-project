"""
共用工具：CSS樣式設定 + 資料讀取
被 dashboard.py 跟 pages/ 底下的分頁共用
"""

import pandas as pd
import streamlit as st

LOG_FILE = "paper_trading_log.csv"

PERIOD_OPTIONS = {
    "今日": ("1d", "5m"),
    "本周": ("5d", "15m"),
    "本月": ("1mo", "1d"),
    "今年至今": ("ytd", "1d"),
    "1年": ("1y", "1d"),
    "5年": ("5y", "1wk"),
}


def inject_base_css():
    st.markdown("""
        <style>
        h1 { font-size: 2.2rem !important; }
        .stMarkdown h4 { font-size: 1.25rem !important; }
        section[data-testid="stSidebar"] .streamlit-expanderHeader,
        section[data-testid="stSidebar"] summary {
            font-size: 0.8rem !important;
            padding: 0.3rem 0.5rem !important;
        }
        section[data-testid="stSidebar"] label p { font-size: 0.8rem !important; }
        div[data-testid="stMetricValue"] { font-size: 1.1rem !important; }
        div[data-testid="column"] { padding: 0 4px !important; }
        div[data-testid="stHorizontalBlock"] { gap: 0.3rem !important; }
        </style>
    """, unsafe_allow_html=True)


def load_log():
    import os
    if not os.path.exists(LOG_FILE):
        return None
    df = pd.read_csv(LOG_FILE, encoding="utf-8-sig")
    df["日期"] = pd.to_datetime(df["日期"])
    df["收盤價"] = pd.to_numeric(df["收盤價"], errors="coerce")
    for col in ["浮動報酬", "來源"]:
        if col not in df.columns:
            df[col] = "" if col == "來源" else pd.NA
    if "浮動報酬" in df.columns:
        df["浮動報酬"] = pd.to_numeric(df["浮動報酬"], errors="coerce")
    df["來源"] = df["來源"].replace("", "追蹤清單").fillna("追蹤清單")
    return df


def sidebar_filter(tickers):
    """把篩選選項收進一個預設收合的展開區塊，不佔用側邊欄空間"""
    with st.sidebar.expander("🔍 篩選", expanded=False):
        selected = st.multiselect("選擇要顯示的商品", tickers, default=tickers)
    return selected

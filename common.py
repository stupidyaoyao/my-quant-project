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
        @import url('https://fonts.googleapis.com/css2?family=Chiron+Sung+HK:wght@400;500;700&display=swap');

        html, body, [class*="css"], .stApp, .stMarkdown, button, input, textarea {
            font-family: 'Chiron Sung HK', serif !important;
        }

        .stApp {
            background:
                radial-gradient(circle at 15% -10%, rgba(99,102,241,0.10) 0%, rgba(14,17,23,0) 40%),
                radial-gradient(circle at 85% -10%, rgba(236,72,153,0.08) 0%, rgba(14,17,23,0) 40%),
                #0e1117 !important;
        }
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

        /* 頂部導覽列：置中、放大字體、選中的分頁用漸層底 */
        div[data-testid="stTopNav"],
        div[role="tablist"],
        header div[role="tablist"] {
            display: flex !important;
            justify-content: center !important;
            width: 100% !important;
            flex: 1 1 auto !important;
        }
        div[data-testid="stTopNav"] button,
        div[role="tablist"] button {
            border-radius: 20px !important;
            margin: 0 4px !important;
            font-size: 1.05rem !important;
            padding: 6px 18px !important;
        }
        div[data-testid="stTopNav"] button p,
        div[role="tablist"] button p {
            font-size: 1.05rem !important;
        }
        div[data-testid="stTopNav"] button[aria-selected="true"],
        div[role="tablist"] button[aria-selected="true"] {
            background: linear-gradient(90deg, #a855f7 0%, #6366f1 100%) !important;
            color: white !important;
        }
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
    with st.sidebar.expander("篩選", expanded=False):
        selected = st.multiselect("選擇要顯示的商品", tickers, default=tickers)
    return selected

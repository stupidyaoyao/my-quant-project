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

        :root {
            --bg-body: #0a100c;
            --bg-panel: oklch(20% 0.025 150);
            --bg-panel-2: oklch(24% 0.03 150);
            --border: oklch(38% 0.03 150 / 0.5);
            --text-primary: oklch(93% 0.01 150);
            --text-secondary: oklch(68% 0.015 150);
            --accent-purple: oklch(58% 0.08 125);
            --accent-pink: oklch(42% 0.07 140);
            --green: oklch(72% 0.19 145);
            --red: oklch(65% 0.22 25);
            --amber: oklch(68% 0.15 70);
            --real-warn: oklch(62% 0.21 35);
        }

        html, body, [class*="css"], .stApp, .stMarkdown, button, input, textarea {
            font-family: 'Chiron Sung HK', serif !important;
            color: var(--text-primary);
        }

        .stApp {
            background:
                radial-gradient(circle at 15% -10%, color-mix(in oklch, var(--accent-purple) 25%, transparent) 0%, transparent 40%),
                radial-gradient(circle at 85% -10%, color-mix(in oklch, var(--accent-pink) 20%, transparent) 0%, transparent 40%),
                var(--bg-body) !important;
        }

        .block-container {
            max-width: 1360px !important;
            padding: 4.5rem 32px 60px !important;
            margin: 0 auto !important;
        }

        h1 { font-size: 20px !important; font-weight: 700 !important; }
        .stMarkdown h4 { font-size: 15px !important; font-weight: 700 !important; }
        div[data-testid="stMetricValue"] { font-size: 28px !important; font-weight: 700 !important; }

        section[data-testid="stSidebar"] {
            background: var(--bg-panel-2) !important;
            width: 260px !important;
            padding: 22px !important;
        }
        section[data-testid="stSidebar"] .streamlit-expanderHeader,
        section[data-testid="stSidebar"] summary {
            font-size: 12px !important;
            padding: 0.3rem 0.5rem !important;
        }
        section[data-testid="stSidebar"] label p { font-size: 12px !important; }

        div[data-testid="column"] { padding: 0 5px !important; }
        div[data-testid="stHorizontalBlock"] { gap: 10px !important; }

        /* 導覽：大分類 + 子分頁，膠囊全圓角，緊密排列 */
        .st-key-nav_group_row div[data-testid="stHorizontalBlock"],
        .st-key-nav_subgroup_row div[data-testid="stHorizontalBlock"] {
            gap: 2px !important;
        }
        .st-key-nav_group_row div[data-testid="column"],
        .st-key-nav_subgroup_row div[data-testid="column"] {
            padding: 0 !important;
            display: flex !important;
            justify-content: center !important;
        }
        .st-key-nav_group_row button,
        .st-key-nav_subgroup_row button {
            border-radius: 999px !important;
            padding: 6px 14px !important;
            font-size: 13px !important;
            font-weight: 600 !important;
        }
        .st-key-nav_group_row button[kind="primary"],
        .st-key-nav_subgroup_row button[kind="primary"] {
            background-color: var(--green) !important;
            border-color: var(--green) !important;
            color: #0a100c !important;
        }
        .st-key-moomoo_nav_btn button[kind="primary"] {
            background-color: var(--amber) !important;
            border-color: var(--amber) !important;
            color: #0a100c !important;
        }
        .st-key-moomoo_nav_btn button[kind="secondary"] {
            border-color: var(--amber) !important;
            color: var(--amber) !important;
        }

        [class*="st-key-grouptoggle_container_"] button {
            font-size: 17px !important;
            font-weight: 700 !important;
            padding: 4px 0 !important;
            border: none !important;
            background: transparent !important;
            text-align: left !important;
        }
        [class*="st-key-grouptoggle_container_"] button:hover {
            color: var(--green) !important;
        }

        /* 導覽：用radio偽裝成緊密排列的膠囊按鈕 */
        .st-key-nav_group_row div[role="radiogroup"],
        .st-key-nav_subgroup_row div[role="radiogroup"] {
            justify-content: center !important;
            gap: 6px !important;
        }
        .st-key-nav_group_row div[role="radiogroup"] label,
        .st-key-nav_subgroup_row div[role="radiogroup"] label {
            border: 1px solid var(--border) !important;
            border-radius: 999px !important;
            padding: 6px 16px !important;
            margin: 0 !important;
            background: transparent !important;
        }
        .st-key-nav_group_row div[role="radiogroup"] label > div:first-child > div:first-child,
        .st-key-nav_subgroup_row div[role="radiogroup"] label > div:first-child > div:first-child {
            display: none !important;
        }
        .st-key-nav_group_row div[role="radiogroup"] label p,
        .st-key-nav_subgroup_row div[role="radiogroup"] label p {
            font-size: 13px !important;
            font-weight: 600 !important;
        }
        .st-key-nav_group_row div[role="radiogroup"] label:has(input:checked),
        .st-key-nav_subgroup_row div[role="radiogroup"] label:has(input:checked) {
            background: linear-gradient(135deg, oklch(0.58 0.08 125), oklch(0.42 0.07 140)) !important;
            border: none !important;
            border-color: transparent !important;
        }
        .st-key-nav_group_row div[role="radiogroup"] label:has(input:checked) p,
        .st-key-nav_subgroup_row div[role="radiogroup"] label:has(input:checked) p {
            color: #ffffff !important;
            font-weight: 700 !important;
        }
        .st-key-nav_group_row div[role="radiogroup"] label:nth-of-type(3):has(input:checked) {
            background: var(--amber) !important;
            border-color: var(--amber) !important;
        }
        .st-key-nav_group_row div[role="radiogroup"] label:nth-of-type(3) {
            border-color: var(--amber) !important;
        }
        .st-key-nav_group_row div[role="radiogroup"] label:nth-of-type(3) p {
            color: var(--amber) !important;
        }
        .st-key-nav_group_row div[role="radiogroup"] label:nth-of-type(3):has(input:checked) p {
            color: #0a100c !important;
        }

        /* 統計卡片 */
        .stat-card {
            border-radius: 14px;
            padding: 18px 20px;
            background: var(--bg-panel);
            border: 1px solid var(--border);
        }
        .stat-card.up { background: color-mix(in oklch, var(--green) 12%, var(--bg-panel)); border-color: color-mix(in oklch, var(--green) 40%, transparent); }
        .stat-card.down { background: color-mix(in oklch, var(--red) 12%, var(--bg-panel)); border-color: color-mix(in oklch, var(--red) 40%, transparent); }
        .stat-label { font-size: 12px; color: var(--text-secondary); margin-bottom: 6px; }
        .stat-value { font-size: 28px; font-weight: 700; }
        .stat-value.up-text { color: var(--green); }
        .stat-value.down-text { color: var(--red); }
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


def sidebar_filter(tickers, key="default"):
    """把篩選選項收進一個預設收合的展開區塊，不佔用側邊欄空間"""
    with st.sidebar.expander("篩選", expanded=False):
        selected = st.multiselect("選擇要顯示的商品", tickers, default=tickers, key=f"sidebar_filter_{key}")
    return selected

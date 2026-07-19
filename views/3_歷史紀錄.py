"""
歷史紀錄頁面（合併版）
------------------------------------
把均線系統(paper_trading_log.csv)跟ORB系統(orb_log.csv)
兩份不同格式的紀錄，統一轉換成同一張表格顯示，可用「策略」篩選。

均線系統只有日期(一天一次)，ORB系統精確到分鐘，
合併表裡均線系統的「時間」欄位會是空的，這是資料本質上的差異，不是bug。
"""

import os
import pandas as pd
import streamlit as st

from common import inject_base_css

inject_base_css()
st.title("歷史紀錄")


def normalize_ma_log(df):
    """把均線系統的紀錄，轉成統一格式。只保留真正的進場/出場事件，不含每日續抱狀態回報"""
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

    out = pd.DataFrame({
        "日期": pd.to_datetime(df["日期"]),
        "時間": "",
        "商品": df["商品"],
        "策略": "均線策略",
        "訊號": df.apply(get_signal, axis=1),
        "價格": pd.to_numeric(df["收盤價"], errors="coerce"),
        "結果": df.apply(get_result, axis=1),
    })
    return out


def normalize_orb_log(df):
    """把ORB系統的紀錄，轉成統一格式"""
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

    out = pd.DataFrame({
        "日期": dt.dt.normalize(),
        "時間": dt.dt.strftime("%H:%M"),
        "商品": df["商品"],
        "策略": "ORB當沖",
        "訊號": df.apply(get_signal, axis=1),
        "價格": pd.to_numeric(df["價格"], errors="coerce"),
        "結果": df.apply(get_result, axis=1),
    })
    return out


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
    st.stop()

combined = pd.concat(frames, ignore_index=True).sort_values(["日期", "時間"], ascending=[False, False])

# ---------- 日期快篩 ----------
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

# ---------- 策略篩選 + 搜尋 ----------
col1, col2 = st.columns([2, 3])
with col1:
    strategy_filter = st.radio("策略", ["全部", "均線策略", "ORB當沖"], horizontal=True)
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


def color_result(val):
    if val == "獲利":
        return "color: #2ecc71; font-weight: 600;"
    elif val == "虧損":
        return "color: #e74c3c; font-weight: 600;"
    return ""


def color_signal(val):
    if val == "進場":
        return "color: #6366f1; font-weight: 600;"
    elif "停損" in str(val):
        return "color: #e74c3c;"
    elif "停利" in str(val) or val == "訊號出場":
        return "color: #2ecc71;"
    return ""


styled = display_df.style.map(color_result, subset=["結果"]).map(color_signal, subset=["訊號"])
st.dataframe(styled, width='stretch', hide_index=True)

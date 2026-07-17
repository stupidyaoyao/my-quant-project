"""
ORB 當沖監控頁面（獨立分頁）
------------------------------------
顯示 orb_monitor.py 產生的盤中訊號紀錄，
沿用主頁面的清單式排版風格。
"""

import os
import pandas as pd
import streamlit as st

from common import inject_base_css

inject_base_css()
st.title("ORB 當沖監控")
st.caption("策略：30分鐘回測確認型，停利2R，僅適用美股（不含加密貨幣）")

LOG_FILE = "orb_log.csv"

if not os.path.exists(LOG_FILE):
    st.warning("還沒有任何紀錄，排程會在美股開盤時段自動產生資料")
    st.stop()

df = pd.read_csv(LOG_FILE, encoding="utf-8-sig")
if df.empty:
    st.info("還沒有任何事件紀錄")
    st.stop()

df["時間"] = pd.to_datetime(df["時間"])
df = df.sort_values("時間", ascending=False)

# ---------- 今日摘要 ----------
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

# ---------- 事件清單（清單式排版，呼應主頁風格） ----------
st.subheader("事件紀錄")

tickers = df["商品"].unique().tolist()
selected = st.multiselect("篩選商品", tickers, default=tickers)
filtered = df[df["商品"].isin(selected)]

for _, row in filtered.iterrows():
    event = row["事件"]
    is_entry = event == "進場"
    is_win_exit = event.startswith("出場") and "R值" in row and pd.notna(row.get("R值")) and float(row.get("R值", 0)) > 0
    is_loss_exit = event.startswith("出場") and "R值" in row and pd.notna(row.get("R值")) and float(row.get("R值", 0)) <= 0

    if is_entry:
        bg = "linear-gradient(90deg, rgba(99,102,241,0.03) 0%, rgba(99,102,241,0.18) 100%)"
        tag_color = "#6366f1"
        tag = "進場"
    elif is_win_exit:
        bg = "linear-gradient(90deg, rgba(46,204,113,0.03) 0%, rgba(46,204,113,0.18) 100%)"
        tag_color = "#2ecc71"
        tag = f"{event}"
    elif is_loss_exit:
        bg = "linear-gradient(90deg, rgba(231,76,60,0.03) 0%, rgba(231,76,60,0.18) 100%)"
        tag_color = "#e74c3c"
        tag = f"{event}"
    else:
        bg = "linear-gradient(90deg, rgba(255,255,255,0.015) 0%, rgba(255,255,255,0.05) 100%)"
        tag_color = "#888"
        tag = event

    r_display = ""
    if pd.notna(row.get("R值")) and str(row.get("R值")) != "":
        try:
            r_val = float(row["R值"])
            r_display = f"<span style='color:{tag_color};font-weight:700;'>{r_val:+.1f}R</span>"
        except (ValueError, TypeError):
            pass

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

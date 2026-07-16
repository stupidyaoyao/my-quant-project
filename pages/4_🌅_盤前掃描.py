"""
盤前爆量股掃描頁面（獨立分頁）
------------------------------------
顯示 premarket_scanner.py 掃描出的盤前爆量股清單，
每檔附上漲跌幅、盤前成交量、上漲原因（新聞標題）。
"""

import json
import os

import streamlit as st

from common import inject_base_css

st.set_page_config(page_title="盤前掃描", layout="wide")
inject_base_css()
st.title("盤前爆量股掃描")

DATA_FILE = "premarket_gappers.json"

if not os.path.exists(DATA_FILE):
    st.warning("還沒有掃描資料，請先執行 python premarket_scanner.py 產生資料")
    st.stop()

with open(DATA_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

scanned_at = data.get("scanned_at", "未知時間")
gappers = data.get("gappers", [])

st.caption(f"掃描時間：{scanned_at}")

if not gappers:
    st.info("目前沒有符合條件的盤前爆量股（漲幅>5%、股價>$3、盤前成交量>5萬股）")
    st.stop()

for g in gappers:
    is_premarket = g.get("is_premarket_data", True)
    data_tag = "" if is_premarket else "（非盤前時段，以當日漲跌幅估算）"

    col1, col2 = st.columns([1, 4])
    with col1:
        st.markdown(
            f"""<div style="border:2px solid #2ecc71;border-radius:10px;padding:12px;
            background-color:rgba(46,204,113,0.10);text-align:center;">
            <div style="font-size:0.85em;color:#888;">#{g['rank']}</div>
            <b style="font-size:1.2em;">{g['symbol']}</b><br>
            <span style="font-size:1.1em;">${g['price']:,.2f}</span><br>
            <span style="color:#2ecc71;font-weight:bold;">▲ {g['gap_pct']:+.2f}%</span>
            </div>""",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(f"**盤前成交量**：{g['premarket_volume']:,}{data_tag}")
        if g.get("catalyst"):
            st.markdown(f"**上漲原因**：{g['catalyst']}")
        else:
            st.markdown("**上漲原因**：無相關新聞")
        for headline in g.get("headlines", [])[1:]:
            st.caption(f"新聞：{headline}")
    st.divider()

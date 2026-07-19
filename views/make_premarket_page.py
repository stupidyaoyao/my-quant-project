"""
輔助程式：建立盤前掃描頁面（函式化版本）
執行方式（在 pages 資料夾裡）：
    python make_premarket_page.py
執行完會覆寫 4_盤前掃描.py，之後這支輔助程式可以刪除。
"""

content = r'''"""盤前爆量股掃描（函式化版本，供 app.py 路由器呼叫）"""

import json
import os
import streamlit as st


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
        rank = g["rank"]
        symbol = g["symbol"]
        price = g["price"]
        gap_pct = g["gap_pct"]
        premarket_volume = g["premarket_volume"]
        is_premarket = g.get("is_premarket_data", True)
        data_tag = "" if is_premarket else "（非盤前時段，以當日漲跌幅估算）"
        catalyst = g.get("catalyst") or "無相關新聞"

        col1, col2 = st.columns([1, 4])
        with col1:
            card_html = (
                '<div style="border:2px solid #2ecc71;border-radius:10px;padding:12px;'
                'background-color:rgba(46,204,113,0.10);text-align:center;">'
                f'<div style="font-size:0.85em;color:#888;">#{rank}</div>'
                f'<b style="font-size:1.2em;">{symbol}</b><br>'
                f'<span style="font-size:1.1em;">${price:,.2f}</span><br>'
                f'<span style="color:#2ecc71;font-weight:bold;">+{gap_pct:.2f}%</span>'
                '</div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)
        with col2:
            st.markdown(f"**盤前成交量**：{premarket_volume:,}{data_tag}")
            st.markdown(f"**上漲原因**：{catalyst}")
            for headline in g.get("headlines", [])[1:]:
                st.caption(headline)
        st.divider()
'''

filename = "4_\u76e4\u524d\u6383\u63cf.py"

with open(filename, "w", encoding="utf-8") as f:
    f.write(content)

print(f"已建立檔案: {filename}")

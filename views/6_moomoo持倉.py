"""moomoo 帳戶持倉（函式化版本，模擬/真實帳戶分開，供 app.py 路由器呼叫）"""

import json
import os
import streamlit as st


def render_row(p):
    pl = p.get("pl", 0)
    pl_ratio = p.get("pl_ratio", 0)
    bg = "rgba(46,204,113,0.12)" if pl >= 0 else "rgba(231,76,60,0.12)"
    color = "#2ecc71" if pl >= 0 else "#e74c3c"
    row_html = (
        f'<div style="display:flex;align-items:center;background:{bg};'
        'border-radius:6px;padding:10px 14px;margin-bottom:6px;">'
        f'<div style="flex:1.3;font-weight:700;">{p["code"]}</div>'
        f'<div style="flex:1.5;color:#888;">{p.get("name", "")}</div>'
        f'<div style="flex:1;">{p["qty"]:.0f} 股</div>'
        f'<div style="flex:1.2;">成本 ${p["cost_price"]:,.2f}</div>'
        f'<div style="flex:1.2;">現價 ${p["current_price"]:,.2f}</div>'
        f'<div style="flex:1.3;color:{color};font-weight:600;">${pl:,.2f}（{pl_ratio:+.2f}%）</div>'
        '</div>'
    )
    st.markdown(row_html, unsafe_allow_html=True)


def render_moomoo():
    st.title("moomoo 帳戶持倉")

    DATA_FILE = "moomoo_positions.json"
    if not os.path.exists(DATA_FILE):
        st.warning("還沒有同步過資料，請在本機執行 python sync_moomoo_positions.py 產生資料")
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    st.caption(f"上次同步時間：{data.get('synced_at', '未知')}（非即時，需在本機OpenD開著時手動同步更新）")

    real = data.get("real")
    st.markdown(
        '<div style="border:2px solid #e74c3c;border-radius:10px;padding:14px 18px;'
        'background:linear-gradient(135deg, rgba(231,76,60,0.15) 0%, rgba(231,76,60,0.04) 100%);'
        'margin-bottom:16px;">'
        '<b style="color:#e74c3c;font-size:1.1em;">警告：真實帳戶（真錢，僅讀取顯示，系統不會對此帳戶下單）</b>'
        '</div>',
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
                render_row(p)

    st.divider()

    st.markdown(
        '<div style="border:1px solid #444;border-radius:10px;padding:10px 18px;margin-bottom:16px;">'
        '<b>模擬帳戶（模擬盤・虛擬資金，非真錢）</b>'
        '</div>',
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
                render_row(p)

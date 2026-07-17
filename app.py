"""
應用程式進入點（頂部導覽版）
------------------------------------
取代原本 pages/ 資料夾自動產生的側邊導覽，
改用 st.navigation(position="top") 讓分頁選單顯示在頂部。

⚠️ 部署到 Streamlit Cloud 時，Main file path 需要改成 app.py（不是 dashboard.py）。

執行方式：
    streamlit run app.py
"""

import streamlit as st

from common import inject_base_css

st.set_page_config(page_title="量化交易模擬儀表板", layout="wide")
inject_base_css()

home = st.Page("dashboard.py", title="總覽", default=True)
news = st.Page("pages/1_News.py", title="新聞")
returns = st.Page("pages/2_報酬率追蹤.py", title="報酬率追蹤")
history = st.Page("pages/3_歷史紀錄.py", title="歷史紀錄")
premarket = st.Page("pages/4_盤前掃描.py", title="盤前掃描")
orb = st.Page("pages/5_ORB當沖.py", title="ORB當沖")

pg = st.navigation([home, news, returns, history, premarket, orb], position="top")
pg.run()

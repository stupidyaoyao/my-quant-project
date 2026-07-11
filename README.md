# 我的量化交易模擬系統

## 🔗 網頁儀表板

https://my-quant-project-dqqyaqdytdd6nna26h939b.streamlit.app/

（手機、電腦都能開，隨時查看最新狀態）

## 系統組成

- **均線+ATR策略**（`paper_trading_daily.py`）：每天自動更新一次，追蹤 BTC/ETH/QQQ/AAPL 等商品
- **ORB當沖策略**（`orb_monitor.py`）：美股開盤時段自動每5分鐘更新一次
- **儀表板**（`dashboard.py` + `pages/`）：Streamlit Cloud 自動部署，隨 GitHub 更新自動同步

## 自動化排程

兩個 GitHub Actions 排程都會自動執行，不需要手動操作：
- Daily Paper Trading Update：每天一次
- ORB Intraday Monitor：美股開盤時段每5分鐘一次

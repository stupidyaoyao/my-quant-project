"""
風控檢查模組
------------------------
在每一次自動下單之前，先通過這裡的檢查，任何一項規則沒過，就拒絕這筆交易。
對應 project_rules.md 裡的硬規則。

⚠️ ALLOW_REAL_TRADING 這個開關永遠是 False，除非使用者在對話裡明確、清楚地
   要求切換成真倉，才手動改成 True——這是最後一道防線，寧可太保守也不要出錯。
"""

import json
import os
from datetime import date

import yfinance as yf

RISK_STATE_FILE = "risk_state.json"

# ---------- 硬規則參數（對應 project_rules.md） ----------
RISK_PER_TRADE_PCT = 0.02       # 單筆風險上限：帳戶資金的2%
DAILY_LOSS_LIMIT_PCT = 0.06     # 每日虧損斷路器：達6%當天停止交易
MAX_CONCURRENT_POSITIONS = 5    # 同時持倉上限
ORB_MAX_DAILY_TRADES = 6        # ORB當沖每日交易次數上限
EARNINGS_BLACKOUT_DAYS = 3      # 財報公布前幾天內不開新倉
ALLOW_REAL_TRADING = False      # 永遠是False，除非明確要求才手動改


def load_risk_state():
    if os.path.exists(RISK_STATE_FILE):
        with open(RISK_STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_risk_state(state):
    with open(RISK_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def ensure_today_state(current_equity):
    """換日就重置每日追蹤的數字（起始權益、交易次數）"""
    state = load_risk_state()
    today_str = str(date.today())
    if state.get("date") != today_str:
        state = {"date": today_str, "starting_equity": current_equity, "trade_count": {}}
        save_risk_state(state)
    return state


def check_daily_loss_breaker(current_equity):
    """規則：每日虧損斷路器"""
    state = ensure_today_state(current_equity)
    starting_equity = state["starting_equity"]
    if starting_equity <= 0:
        return True, ""
    drawdown = (starting_equity - current_equity) / starting_equity
    if drawdown >= DAILY_LOSS_LIMIT_PCT:
        return False, f"今日虧損已達{drawdown:.1%}，觸發每日虧損斷路器（上限{DAILY_LOSS_LIMIT_PCT:.0%}），今天停止交易"
    return True, ""


def check_max_positions(current_position_count):
    """規則：同時持倉上限"""
    if current_position_count >= MAX_CONCURRENT_POSITIONS:
        return False, f"目前已持有{current_position_count}個部位，達到上限（{MAX_CONCURRENT_POSITIONS}），不再開新倉"
    return True, ""


def check_daily_trade_count(strategy_name, current_equity):
    """規則：ORB每日交易次數上限（均線系統一天本來就只判斷一次，不受此限制）"""
    if strategy_name != "ORB":
        return True, ""
    state = ensure_today_state(current_equity)
    count = state["trade_count"].get(strategy_name, 0)
    if count >= ORB_MAX_DAILY_TRADES:
        return False, f"{strategy_name}今日已交易{count}筆，達到上限（{ORB_MAX_DAILY_TRADES}），不再開新倉"
    return True, ""


def record_trade(strategy_name, current_equity):
    """下單成功後呼叫，累計今日交易次數"""
    state = ensure_today_state(current_equity)
    state["trade_count"][strategy_name] = state["trade_count"].get(strategy_name, 0) + 1
    save_risk_state(state)


def check_earnings_soon(ticker, days_ahead=EARNINGS_BLACKOUT_DAYS):
    """規則：已知財報公布日不開新倉。抓不到財報日期就放行，避免資料源問題誤擋所有交易"""
    try:
        cal = yf.Ticker(ticker).calendar
        if cal and "Earnings Date" in cal:
            earnings_dates = cal["Earnings Date"]
            if not isinstance(earnings_dates, list):
                earnings_dates = [earnings_dates]
            for ed in earnings_dates:
                if ed is None:
                    continue
                days_until = (ed - date.today()).days
                if 0 <= days_until <= days_ahead:
                    return False, f"{ticker}財報將在{days_until}天內公布（{ed}），暫不開新倉"
    except Exception:
        pass
    return True, ""


def calculate_position_size(entry_price, stop_price, net_assets):
    """
    規則：不使用槓桿。永遠依net_assets（實際資產）計算部位大小，
    完全不採用moomoo顯示的buying_power（含槓桿的購買力）
    """
    risk = abs(entry_price - stop_price)
    if risk <= 0 or net_assets <= 0:
        return 0
    risk_amount = net_assets * RISK_PER_TRADE_PCT
    shares_by_risk = int(risk_amount / risk)
    shares_by_capital = int(net_assets / entry_price)  # 不能超過實際資產能買的數量
    return max(0, min(shares_by_risk, shares_by_capital))


def pretrade_check(strategy_name, ticker, current_equity, current_position_count):
    """
    下單前的總檢查，全部通過才回傳 True。
    回傳: (是否允許, 拒絕原因列表)
    """
    reasons = []
    for check_fn, args in [
        (check_daily_loss_breaker, (current_equity,)),
        (check_max_positions, (current_position_count,)),
        (check_daily_trade_count, (strategy_name, current_equity)),
        (check_earnings_soon, (ticker,)),
    ]:
        ok, reason = check_fn(*args)
        if not ok:
            reasons.append(reason)
    return len(reasons) == 0, reasons


def safe_place_order(trd_ctx, acc_id, code, qty, direction, order_type_market=True):
    """
    安全下單包裝：無論外部怎麼呼叫，永遠強制使用 SIMULATE 環境，
    除非 ALLOW_REAL_TRADING 被明確改成 True（且需要使用者在對話中明確授權）。
    """
    import moomoo as ft

    trd_env = ft.TrdEnv.REAL if ALLOW_REAL_TRADING else ft.TrdEnv.SIMULATE
    if trd_env == ft.TrdEnv.REAL:
        print("⚠️⚠️⚠️ 警告：即將在真實帳戶下單！⚠️⚠️⚠️")

    trd_side = ft.TrdSide.BUY if direction == "long" else ft.TrdSide.SELL
    order_type = ft.OrderType.MARKET if order_type_market else ft.OrderType.NORMAL

    ret, data = trd_ctx.place_order(
        price=0, qty=qty, code=code, trd_side=trd_side,
        order_type=order_type, trd_env=trd_env, acc_id=acc_id,
    )
    return ret, data

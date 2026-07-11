"""
樣本內 / 樣本外驗證 + 停損比例穩健性測試
------------------------------------------
測試不同停損比例，同時在樣本內、樣本外資料上跑，
確認某個停損比例的效果不是「剛好套中特定事件」的巧合。

執行方式：
    python is_oos_backtest.py
"""

import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "SimHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False

# ---------- 參數設定 ----------
TICKER = "INTC"
START_DATE = "2018-01-01"
SPLIT_DATE = "2023-01-01"
END_DATE = "2025-01-01"
SHORT_WINDOW = 20
LONG_WINDOW = 60
INITIAL_CAPITAL = 10000
STOP_LOSS_OPTIONS = [None, 0.08, 0.10, 0.15, 0.20, 0.25, 0.30]  # None = 不設停損


def fetch_data(ticker, start, end):
    df = yf.download(ticker, start=start, end=end, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Close"]].dropna()
    return df


def generate_signals(df, short_window, long_window):
    df = df.copy()
    df["MA_short"] = df["Close"].rolling(window=short_window).mean()
    df["MA_long"] = df["Close"].rolling(window=long_window).mean()
    df["signal"] = 0
    df.loc[df["MA_short"] > df["MA_long"], "signal"] = 1
    df["position"] = df["signal"].diff()
    return df


def backtest_with_stop_loss(df, initial_capital, stop_loss_pct):
    """逐日模擬交易，加入停損規則；stop_loss_pct=None 代表不設停損"""
    capital = initial_capital
    in_position = False
    entry_price = entry_capital = None
    equity_list = []
    num_trades = 0
    num_stop_exits = 0

    for _, row in df.iterrows():
        price = row["Close"]
        if not in_position:
            equity_list.append(capital)
            if row["signal"] == 1:
                in_position = True
                entry_price, entry_capital = price, capital
        else:
            current_return = price / entry_price - 1
            stop_triggered = (stop_loss_pct is not None) and (current_return <= -stop_loss_pct)
            ma_exit = row["signal"] == 0
            if stop_triggered or ma_exit:
                capital = entry_capital * (1 + current_return)
                num_trades += 1
                if stop_triggered:
                    num_stop_exits += 1
                in_position = False
                equity_list.append(capital)
            else:
                equity_list.append(entry_capital * (1 + current_return))

    equity_curve = pd.Series(equity_list, index=df.index)
    total_return = equity_curve.iloc[-1] / initial_capital - 1
    running_max = equity_curve.cummax()
    max_drawdown = ((equity_curve - running_max) / running_max).min()
    years = (df.index[-1] - df.index[0]).days / 365.25
    cagr = (1 + total_return) ** (1 / years) - 1

    return {
        "total_return": total_return,
        "cagr": cagr,
        "max_drawdown": max_drawdown,
        "num_trades": num_trades,
        "num_stop_exits": num_stop_exits,
    }


def print_sensitivity_table(df, label, buy_hold_return):
    print(f"===== {label}：不同停損比例的表現 =====")
    print(f"{'停損比例':<10}{'總報酬率':>10}{'年化報酬':>10}{'最大回撤':>10}{'交易次數':>8}{'停損次數':>8}")
    for sl in STOP_LOSS_OPTIONS:
        r = backtest_with_stop_loss(df, INITIAL_CAPITAL, sl)
        sl_label = "不設停損" if sl is None else f"{sl:.0%}"
        print(f"{sl_label:<10}{r['total_return']:>10.2%}{r['cagr']:>10.2%}"
              f"{r['max_drawdown']:>10.2%}{r['num_trades']:>8}{r['num_stop_exits']:>8}")
    print(f"（對照：買進持有總報酬率 {buy_hold_return:.2%}）")
    print()


if __name__ == "__main__":
    full_data = fetch_data(TICKER, START_DATE, END_DATE)
    full_data = generate_signals(full_data, SHORT_WINDOW, LONG_WINDOW)

    df_in = full_data.loc[:SPLIT_DATE]
    df_out = full_data.loc[SPLIT_DATE:]

    bh_in = df_in["Close"].iloc[-1] / df_in["Close"].iloc[0] - 1
    bh_out = df_out["Close"].iloc[-1] / df_out["Close"].iloc[0] - 1

    print_sensitivity_table(df_in, "樣本內 (2018-2023)", bh_in)
    print_sensitivity_table(df_out, "樣本外 (2023-2025)", bh_out)

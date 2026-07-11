"""
簡單均線交叉策略回測範例
------------------------
這是你的第一個量化交易程式，目標是：
  1. 抓取美股歷史資料 (使用 yfinance)
  2. 計算短期/長期均線
  3. 均線黃金交叉 = 買進訊號，死亡交叉 = 賣出訊號
  4. 計算回測績效 (總報酬、最大回撤) 並畫圖比較

執行方式：
    pip install yfinance pandas matplotlib
    python simple_ma_backtest.py
"""

import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt

# ---------- 中文字型設定：避免圖表中文變成方框 ----------
# Windows 內建「微軟正黑體」；Mac 可改成 "PingFang TC" 或 "Heiti TC"
plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "SimHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False  # 避免負號顯示異常

# ---------- 參數設定：這些是你之後最常調整的地方 ----------
TICKER = "AAPL"            # 想測試的股票代號，可以換成 MSFT、TSLA 等
START_DATE = "2020-01-01"
END_DATE = "2025-01-01"
SHORT_WINDOW = 20          # 短期均線天數
LONG_WINDOW = 60           # 長期均線天數
INITIAL_CAPITAL = 10000    # 假設的初始資金 (美元)


def fetch_data(ticker, start, end):
    """第一步：抓取歷史股價資料"""
    df = yf.download(ticker, start=start, end=end, auto_adjust=True)
    df = df[["Close"]].dropna()
    return df


def generate_signals(df, short_window, long_window):
    """第二步：計算均線，產生買賣訊號"""
    df["MA_short"] = df["Close"].rolling(window=short_window).mean()
    df["MA_long"] = df["Close"].rolling(window=long_window).mean()

    df["signal"] = 0
    df.loc[df["MA_short"] > df["MA_long"], "signal"] = 1  # 1 = 持有部位
    df["position"] = df["signal"].diff()  # 1 = 買進當天, -1 = 賣出當天
    return df


def backtest(df, initial_capital):
    """第三步：計算策略績效，並跟「單純買進持有」比較"""
    df["daily_return"] = df["Close"].pct_change()
    # shift(1) 避免用到「當天還沒發生」的訊號，這是新手最常犯的錯誤之一
    df["strategy_return"] = df["daily_return"] * df["signal"].shift(1)

    df["equity_curve"] = (1 + df["strategy_return"]).cumprod() * initial_capital
    df["buy_hold_curve"] = (1 + df["daily_return"]).cumprod() * initial_capital

    total_return = df["equity_curve"].iloc[-1] / initial_capital - 1
    buy_hold_return = df["buy_hold_curve"].iloc[-1] / initial_capital - 1

    running_max = df["equity_curve"].cummax()
    drawdown = (df["equity_curve"] - running_max) / running_max
    max_drawdown = drawdown.min()

    print(f"===== {TICKER} 均線交叉策略回測結果 =====")
    print(f"策略總報酬率:       {total_return:.2%}")
    print(f"買進持有總報酬率:   {buy_hold_return:.2%}")
    print(f"策略最大回撤:       {max_drawdown:.2%}")

    return df


def plot_results(df, ticker):
    """第四步：畫圖，直覺檢查策略邏輯有沒有問題"""
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    axes[0].plot(df.index, df["Close"], label="收盤價", alpha=0.5)
    axes[0].plot(df.index, df["MA_short"], label=f"MA{SHORT_WINDOW}")
    axes[0].plot(df.index, df["MA_long"], label=f"MA{LONG_WINDOW}")

    buy_signals = df[df["position"] == 1]
    sell_signals = df[df["position"] == -1]
    axes[0].scatter(buy_signals.index, buy_signals["Close"], marker="^",
                     color="green", label="買進", zorder=5)
    axes[0].scatter(sell_signals.index, sell_signals["Close"], marker="v",
                     color="red", label="賣出", zorder=5)
    axes[0].set_title(f"{ticker} 均線交叉策略")
    axes[0].legend()

    axes[1].plot(df.index, df["equity_curve"], label="策略資金曲線")
    axes[1].plot(df.index, df["buy_hold_curve"], label="買進持有資金曲線", alpha=0.7)
    axes[1].set_title("資金曲線比較")
    axes[1].legend()

    plt.tight_layout()
    plt.savefig("backtest_result.png", dpi=150)
    print("\n圖表已儲存為 backtest_result.png，打開來看看買賣點位對不對！")


if __name__ == "__main__":
    data = fetch_data(TICKER, START_DATE, END_DATE)
    data = generate_signals(data, SHORT_WINDOW, LONG_WINDOW)
    data = backtest(data, INITIAL_CAPITAL)
    plot_results(data, TICKER)

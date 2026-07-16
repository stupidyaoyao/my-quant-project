"""
moomoo 追蹤清單同步程式
------------------------
每次在電腦開著、OpenD 登入時執行這支程式，
會把你 moomoo App 裡所有自訂分組的股票，
彙整成一個檔案 (moomoo_watchlist.json)。

之後把這個檔案上傳到 GitHub，
雲端的 paper_trading_daily.py 就會自動一併追蹤這些股票。

執行方式：
    python sync_moomoo_watchlist.py
"""

import json
import moomoo as ft

OPEND_HOST = "127.0.0.1"
OPEND_PORT = 11111
OUTPUT_FILE = "moomoo_watchlist.json"


def strip_market_prefix(code):
    """moomoo的代號格式是「市場.代號」，例如 US.AAOI，我們只需要後面的代號部分"""
    if "." in code:
        return code.split(".", 1)[1]
    return code


def main():
    print("正在連線到 OpenD...")
    quote_ctx = ft.OpenQuoteContext(host=OPEND_HOST, port=OPEND_PORT)
    all_tickers = []

    try:
        ret, groups = quote_ctx.get_user_security_group(ft.UserSecurityGroupType.CUSTOM)
        if ret != ft.RET_OK:
            print(f"⚠️ 讀取分組失敗: {groups}")
            return

        for _, row in groups.iterrows():
            group_name = row["group_name"]
            ret2, stocks = quote_ctx.get_user_security(group_name)
            if ret2 == ft.RET_OK and len(stocks) > 0:
                tickers_in_group = [strip_market_prefix(code) for code in stocks["code"]]
                for t in tickers_in_group:
                    if t not in all_tickers:
                        all_tickers.append(t)
                print(f"分組「{group_name}」：{len(stocks)} 檔 -> {tickers_in_group}")
            else:
                print(f"分組「{group_name}」：空的，略過")

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump({"tickers": all_tickers}, f, ensure_ascii=False, indent=2)

        print(f"\n✅ 已同步 {len(all_tickers)} 檔股票到 {OUTPUT_FILE}")
        print(all_tickers)

    finally:
        quote_ctx.close()


if __name__ == "__main__":
    main()

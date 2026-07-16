"""
moomoo API 連線測試
------------------------
第一步：確認 Python 能透過 OpenD 連上你的 moomoo 帳號，
並嘗試讀取你在 App 裡設定的追蹤清單(自選股)。

前置作業：
  1. moomoo OpenD 視窗必須保持開著、顯示 "Connected"
  2. 安裝套件： pip install moomoo-api

執行方式：
    python moomoo_test.py
"""

import moomoo as ft

OPEND_HOST = "127.0.0.1"
OPEND_PORT = 11111


def main():
    print("正在連線到 OpenD...")
    quote_ctx = ft.OpenQuoteContext(host=OPEND_HOST, port=OPEND_PORT)

    try:
        print("\n===== 嘗試讀取追蹤清單分組 =====")
        ret, data = quote_ctx.get_user_security_group(ft.UserSecurityGroupType.CUSTOM)
        print(f"回傳狀態: {ret}")
        print(data)

        if ret == ft.RET_OK and len(data) > 0:
            for _, row in data.iterrows():
                group_name = row["group_name"]
                print(f"\n----- 分組: {group_name} -----")
                ret2, stocks = quote_ctx.get_user_security(group_name)
                if ret2 == ft.RET_OK:
                    print(stocks)
                else:
                    print(f"讀取失敗: {stocks}")
        else:
            print("沒有找到自訂分組，可能你的追蹤清單都在系統預設分組裡，換個方式再試一次:")
            ret3, data3 = quote_ctx.get_user_security_group(ft.UserSecurityGroupType.SYSTEM)
            print(f"系統分組回傳狀態: {ret3}")
            print(data3)

    except Exception as e:
        print(f"⚠️ 發生錯誤: {e}")
    finally:
        quote_ctx.close()
        print("\n連線已關閉")


if __name__ == "__main__":
    main()

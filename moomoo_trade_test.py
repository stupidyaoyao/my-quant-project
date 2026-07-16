"""
moomoo 交易連線測試（模擬帳戶）
------------------------------------
只測試「交易連線」本身，讀取模擬帳戶的資金、持倉，
確認連線正常，這一步還不會真的下單。

前置作業：
  moomoo OpenD 視窗必須保持開著、顯示 "Connected"

執行方式：
    python moomoo_trade_test.py
"""

import moomoo as ft

OPEND_HOST = "127.0.0.1"
OPEND_PORT = 11111


def main():
    print("正在連線交易介面...")
    trd_ctx = ft.OpenSecTradeContext(
        filter_trdmarket=ft.TrdMarket.US,
        host=OPEND_HOST,
        port=OPEND_PORT,
        security_firm=ft.SecurityFirm.FUTUSECURITIES,
    )

    try:
        print("\n===== 讀取交易帳戶清單 =====")
        ret, acc_list = trd_ctx.get_acc_list()
        print(f"回傳狀態: {ret}")
        print(acc_list)

        if ret != ft.RET_OK:
            print("讀取帳戶清單失敗，先確認 OpenD 是否正常連線")
            return

        sim_accounts = acc_list[acc_list["trd_env"] == "SIMULATE"]
        if sim_accounts.empty:
            print("⚠️ 沒有找到模擬交易帳戶")
            return

        acc_id = sim_accounts.iloc[0]["acc_id"]
        print(f"\n找到模擬帳戶，acc_id = {acc_id}")

        print("\n===== 讀取帳戶資金 =====")
        ret2, funds = trd_ctx.accinfo_query(trd_env=ft.TrdEnv.SIMULATE, acc_id=acc_id)
        print(f"回傳狀態: {ret2}")
        print(funds)

        print("\n===== 讀取目前持倉 =====")
        ret3, positions = trd_ctx.position_list_query(trd_env=ft.TrdEnv.SIMULATE, acc_id=acc_id)
        print(f"回傳狀態: {ret3}")
        print(positions)

    except Exception as e:
        print(f"⚠️ 發生錯誤: {e}")
    finally:
        trd_ctx.close()
        print("\n連線已關閉")


if __name__ == "__main__":
    main()

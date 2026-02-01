# 該檔案為測試將使用者的消費紀錄從資料庫抓出來存成excel
# 預設使用者id為6,也就是user2的所有資料。
import sys
import os
import pandas as pd
from sqlalchemy.orm import Session

# 將當前目錄（根目錄）加入 Python 搜尋路徑
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# 加上 web_app. 前綴，讓 Python 知道去資料夾裡找
# 這能配合妳 models.py 裡面的 ..database 相對路徑
try:
    from web_app.database import SessionLocal
    from web_app.models import AddRecord

    print("✅ 成功連接到 web_app 模組")
except ImportError as e:
    print(f"❌ 模組引入失敗：{e}")
    print("請確認妳在 money-api 根目錄執行此腳本")
    sys.exit(1)


def run_local_test():
    db = SessionLocal()
    try:
        # 模擬測試 user_id
        target_user_id = 6
        print(f"🚀 開始抓取 user_id: {target_user_id} 的紀錄...")

        # 執行查詢
        records = db.query(AddRecord).filter(AddRecord.user_id == target_user_id).all()

        if not records:
            print("⚠️ 找不到該使用者的收支資料，請檢查資料庫內容。")
            return

        # 妳要求的 True/False 轉換邏輯
        data = []
        for r in records:
            data.append(
                {
                    "日期": r.add_date,
                    "類型": "💰 收入" if r.add_type else "💸 支出",
                    "金額": float(r.add_amount),
                    "分類": r.add_class,
                    "成員": r.add_member,
                    "備註": r.add_note or "-",
                }
            )

        # 產出 Excel
        df = pd.DataFrame(data)
        file_name = "test_export_result.xlsx"
        df.to_excel(file_name, index=False, engine="openpyxl")

        print(f"✨ 測試成功！檔案已產生：{os.path.join(current_dir, file_name)}")
        print(f"📊 統計：共匯出 {len(records)} 筆紀錄。")

    except Exception as e:
        print(f"💥 執行過程發生錯誤：{e}")
    finally:
        db.close()


if __name__ == "__main__":
    run_local_test()

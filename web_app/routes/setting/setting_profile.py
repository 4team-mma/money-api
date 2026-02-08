import os
import shutil
from fastapi import APIRouter, UploadFile, File, Depends
from sqlalchemy.orm import Session

# 這裡要匯入你定義 get_db 的地方，以及你的 Model
# 從上一層匯入 database.py 裡的 get_db
from ...database import get_db
from ... import models



router = APIRouter()

# 1. 取得目前檔案的絕對路徑 (在 routes/setting/ 裡)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. 正確的路徑邏輯：
# 第一個 ".." 回到 routes/
# 第二個 ".." 回到 web_app/ (專案根目錄)
# 這樣才能正確對準最外層的 static
UPLOAD_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", "static", "ProfilePicture"))

# 確保目錄存在
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/upload-avatar/{user_id}")
async def upload_avatar(
    user_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)
):
    # 1. 確保資料夾存在
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)

    # 2. 處理檔名 (建議加上 user_id 避免衝突)
    extension = os.path.splitext(file.filename)[1]
    filename = f"user_{user_id}{extension}"
    file_path = os.path.join(UPLOAD_DIR, filename)

    # 3. 儲存實體檔案到 static/ProfilePicture
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 4. 準備存入 MySQL 的 URL 路徑 (前端存取用)
    # 格式通常為: /static/ProfilePicture/user_1.jpg
    db_url = f"/static/ProfilePicture/{filename}"

    # --- 關鍵：更新 MySQL 資料庫 ---
    # 1. 尋找該使用者的設定資料
    setting = db.query(models.Setting).filter(models.Setting.user_id == user_id).first()

    if setting:
        # 2. 如果找到了，更新 avatar_url 欄位
        setting.avatar_url = db_url
        db.commit()  # 這一行一定要寫，資料才會真的寫進 MySQL
        db.refresh(setting)
    else:
        # 如果該使用者還沒有設定資料，可以考慮幫他建立一筆 (選做)
        new_setting = models.Setting(user_id=user_id, avatar_url=db_url)
        db.add(new_setting)
        db.commit()
    return {"message": "上傳成功", "avatar_url": db_url}


@router.post("/remove-avatar/{user_id}")
async def remove_avatar(user_id: int):
    # 1. 更新資料庫為空值 (或預設圖片路徑)
    # db_query = "UPDATE settings SET avatar_url = NULL WHERE user_id = %s"

    # 2. (選做) 刪除伺服器上的實體檔案以節省空間
    # if os.path.exists(file_path): os.remove(file_path)

    return {"message": "照片已移除"}

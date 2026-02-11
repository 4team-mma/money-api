import os
import shutil
from fastapi import APIRouter, UploadFile, File, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

# 這裡要匯入你定義 get_db 的地方，以及你的 Model
# 從上一層匯入 database.py 裡的 get_db
from ...database import get_db
from ... import models


router = APIRouter()

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# routes/setting → routes → web_app（專案根目錄）
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

UPLOAD_DIR = os.path.join(PROJECT_ROOT, "static", "ProfilePicture")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# =========================
# 📤 上傳頭像 (改用 username)
# =========================
@router.post("/upload-avatar/{username}")
async def upload_avatar(
    username: str, # 改為接收 username
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    # 1️⃣ 根據 username 抓取 user_id
    member = db.query(models.Member).filter(models.Member.username == username).first()
    if not member:
        return {"success": False, "message": "找不到該使用者"}
    user_id = member.user_id

    # 2️⃣ 組檔名與路徑
    extension = os.path.splitext(file.filename)[1]
    filename = f"user_{user_id}{extension}"
    file_path = os.path.join(UPLOAD_DIR, filename)

    # 3️⃣ 存實體檔案
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    db_url = f"/static/ProfilePicture/{filename}"

    # 4️⃣ 更新或建立 setting
    setting = db.query(models.Setting).filter(models.Setting.user_id == user_id).first()

    if setting:
        setting.avatar_url = db_url
    else:
        setting = models.Setting(user_id=user_id, avatar_url=db_url)
        db.add(setting)

    db.commit()
    db.refresh(setting)
    return {"success": True, "message": "上傳成功", "avatar_url": db_url}


# =========================
# 🗑️ 移除頭像 (改用 username)
# =========================
@router.post("/remove-avatar/{username}")
async def remove_avatar(
    username: str, # 改為接收 username
    db: Session = Depends(get_db)
):
    try:
        # 1️⃣ 根據 username 抓取 user_id
        member = db.query(models.Member).filter(models.Member.username == username).first()
        if not member:
            return {"success": False, "message": "找不到該使用者"}

        user_id = member.user_id

        # 2️⃣ 找 Setting 資料
        setting = db.query(models.Setting).filter(models.Setting.user_id == user_id).first()

        if not setting or not setting.avatar_url:
            return {"success": False, "message": "沒有可刪除的頭像"}

        # 3️⃣ 刪除實體檔案
        filename = os.path.basename(setting.avatar_url)
        file_path = os.path.join(UPLOAD_DIR, filename)

        if os.path.exists(file_path):
            os.remove(file_path)

        # 4️⃣ 清空 DB
        setting.avatar_url = None
        db.commit()

        return {"success": True, "message": "頭像已移除"}

    except Exception as e:
        db.rollback()
        return {"success": False, "message": str(e)}
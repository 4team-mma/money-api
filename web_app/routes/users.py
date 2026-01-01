# web_app/routes/users.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from ..database import get_db
from ..models import Member
from ..schemas.member import MemberResponse, MemberUpdate

router = APIRouter()

# 取得所有用戶 (供管理後台列表使用)
@router.get("/", response_model=List[MemberResponse])
def get_all_users(db: Session = Depends(get_db)):
    """取得資料庫中所有成員的完整清單"""
    return db.query(Member).all()

# 更新用戶資訊 (這就是你要的「真修」邏輯)
@router.put("/{user_id}", response_model=MemberResponse)
def update_member_profile(user_id: int, data: MemberUpdate, db: Session = Depends(get_db)):
    # 1. 尋找使用者
    user = db.query(Member).filter(Member.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="找不到該使用者")

    # 2. 更新欄位 (exclude_unset=True 會確保前端沒傳的欄位不會被蓋成空值)
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)

    try:
        db.commit()
        db.refresh(user)
        return user
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"資料庫更新失敗: {str(e)}")

# --- 以下為使用者個人功能 ---
@router.get("/me")
async def get_me():
    return {"username": "當前用戶", "email": "user@example.com"}
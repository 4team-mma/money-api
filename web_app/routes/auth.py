from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Member # 💡 確保 models.py 已經有 Member
from ..schemas.member import MemberRegister, MemberLogin

# 需要在這裡寫守門員涵式 通常叫 get_current_user
# 負責檢查 Header 有沒有 Token、過期了沒，並解碼出 user_id。
async def admin_required():
    """管理員權限驗證依賴項"""
    return True

router = APIRouter()

@router.post("/register")
async def register(data: MemberRegister, db: Session = Depends(get_db)):
    # ... 註冊邏輯 ...
    return {"msg": "註冊成功"}

@router.post("/login")
async def login(data: MemberLogin, db: Session = Depends(get_db)):
    # ... 登入邏輯 ...
    return {"msg": "登入成功"}
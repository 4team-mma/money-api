# web_app/routes/users.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

# 引用路徑維持不變
from ..database import get_db
from ..models import (
    Member,
    AddRecord,
    Account,
    Transaction,
    Notification,
    Feedback,
    PasswordReset,
)
from ..schemas.member import MemberResponse, MemberUpdate, MemberPasswordChange
from ..dependencies import get_current_user
from ..utils.password import verify_password, get_password_hash

router = APIRouter()


# 1. 取得所有用戶 (已修復資安漏洞：加上權限檢查)
@router.get("/", response_model=List[MemberResponse])
def get_all_users(
    db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)
):
    """
    取得資料庫中所有成員的完整清單
    🔒 限制：僅限管理員 (admin) 存取
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="權限不足，僅限管理員存取")

    return db.query(Member).all()


# 2. 更新用戶資訊
@router.put("/{user_id}", response_model=MemberResponse)
def update_member_profile(
    user_id: int,
    data: MemberUpdate,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    # 安全檢查：只有本人或管理員可以修改
    if current_user.user_id != user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="你沒有權限修改此帳號")

    # 尋找使用者
    user = db.query(Member).filter(Member.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="找不到該使用者")

    # 更新欄位 (exclude_unset=True 確保前端沒傳的欄位不會被蓋成空值)
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user


# --- 以下為使用者個人功能 ---


# 3. 取得個人資料 (已優化：直接回傳 current_user，不需重複查庫)
@router.get("/me", response_model=MemberResponse)
def get_me(current_user: Member = Depends(get_current_user)):
    """取得目前登入使用者的資訊"""
    return current_user


# 4. 修改密碼
@router.put("/me/password", summary="變更個人密碼")
async def change_password(
    data: MemberPasswordChange,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    # 驗證舊密碼是否正確
    if not verify_password(data.current_password, current_user.password):
        raise HTTPException(status_code=400, detail="目前密碼輸入錯誤")

    # 加密新密碼
    current_user.password = get_password_hash(data.new_password)

    db.commit()
    return {"message": "密碼變更成功"}


# 5. 刪除個人帳號 (已重構：移除 try-except，交由全域處理器)
@router.delete(
    "/me", summary="刪除目前登入的帳號", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_my_account(
    db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)
):
    # 1. 先刪除該使用者的所有關聯紀錄
    # (如果 Models 有設定 cascade="all, delete" 其實不用手寫這些，但手寫比較保險)
    db.query(AddRecord).filter(AddRecord.user_id == current_user.user_id).delete()
    db.query(Account).filter(Account.user_id == current_user.user_id).delete()
    db.query(Transaction).filter(Transaction.user_id == current_user.user_id).delete()
    db.query(Notification).filter(Notification.user_id == current_user.user_id).delete()
    db.query(Feedback).filter(Feedback.user_id == current_user.user_id).delete()
    db.query(PasswordReset).filter(
        PasswordReset.user_id == current_user.user_id
    ).delete()

    # 2. 刪除會員本人
    db.delete(current_user)

    # 3. 提交
    # 如果這裡發生資料庫錯誤 (如 Foreign Key 限制)，全域處理器會自動 Rollback 並 Log
    db.commit()

    return None

# web_app/routes/users.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
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


# 取得所有用戶 (供管理後台列表使用)
@router.get("/", response_model=List[MemberResponse])
def get_all_users(db: Session = Depends(get_db)):
    """取得資料庫中所有成員的完整清單"""
    return db.query(Member).all()


# 更新用戶資訊
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

    # 1. 尋找使用者
    user = db.query(Member).filter(Member.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="找不到該使用者")

    # 2. 更新欄位 (exclude_unset=True 會確保前端沒傳的欄位不會被蓋成空值)
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user


# --- 以下為使用者個人功能 ---
@router.get("/me")
def get_me(
    db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)
):
    # 用 user_id 去資料庫查名字
    user = db.query(Member).filter(Member.user_id == current_user.user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="找不到使用者")

    # 回傳使用者的資料 (FastAPI 會自動轉成 JSON)
    return user


# --- 修改密碼 ---
@router.put("/me/password", summary="變更個人密碼")
async def change_password(
    data: MemberPasswordChange,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    # 1. 驗證舊密碼是否正確
    if not verify_password(data.current_password, current_user.password):
        raise HTTPException(status_code=400, detail="目前密碼輸入錯誤")

    # 2. 加密新密碼
    current_user.password = get_password_hash(data.new_password)

    db.commit()
    return {"message": "密碼變更成功"}


# --- 刪除個人帳號 (更安全的寫法) ---
@router.delete(
    "/me", summary="刪除目前登入的帳號", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_my_account(
    db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)
):
    try:
        # 1. 先刪除該使用者的所有記帳紀錄
        db.query(AddRecord).filter(AddRecord.user_id == current_user.user_id).delete()

        # 刪除資產帳戶紀錄
        db.query(Account).filter(Account.user_id == current_user.user_id).delete()

        # 刪除轉帳紀錄
        db.query(Transaction).filter(
            Transaction.user_id == current_user.user_id
        ).delete()

        # 刪除提醒紀錄
        db.query(Notification).filter(
            Notification.user_id == current_user.user_id
        ).delete()
        # 💡 如果還有其他關聯資料表（例如 Accounts），也要在這裡一併刪除

        # 刪除回饋關聯
        db.query(Feedback).filter(Feedback.user_id == current_user.user_id).delete()
        # 刪除忘記密碼關聯
        db.query(PasswordReset).filter(
            PasswordReset.user_id == current_user.user_id
        ).delete()

        # 2. 刪除會員本人
        db.delete(current_user)

        db.commit()
        return None
    except Exception as e:
        db.rollback()
        # 輸出詳細錯誤到控制台，方便 Leader 妳除錯
        print(f"❌ 刪除帳號失敗，詳細原因: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"資料庫刪除失敗，請檢查是否有其他關聯資料未清除。",
        )

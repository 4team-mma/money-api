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

# 1. 取得所有用戶
@router.get("/", response_model=List[MemberResponse], summary="👥 取得所有成員清單")
def get_all_users(
    db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)
):
    """
    取得資料庫中所有成員的完整清單。

    - **權限限制**: 🔒 僅限管理員 (`admin`) 存取。
    - **回傳內容**: 包含所有使用者的基本資料、等級(XP)與職稱。
    - **資安等級**: 高。
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="權限不足，僅限管理員存取")

    return db.query(Member).all()

# 2. 更新用戶資訊
@router.put("/{user_id}", response_model=MemberResponse, summary="📝 更新用戶資料")
def update_member_profile(
    user_id: int,
    data: MemberUpdate,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    """
    修改指定使用者的個人資料。

    - **修改權限**: 
        1. 僅限**本人**修改自己的資料。
        2. **管理員**可修改任何人的資料。
    - **更新機制**: 僅更新有傳入的欄位，其餘保持不變。
    - **支援欄位**: `username`, `name`, `email`, `job`。
    """
    # 安全檢查
    if current_user.user_id != user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="你沒有權限修改此帳號")

    user = db.query(Member).filter(Member.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="找不到該使用者")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user

# 3. 取得個人資料
@router.get("/me", response_model=MemberResponse, summary="👤 取得當前個人資料")
def get_me(current_user: Member = Depends(get_current_user)):
    """
    快速取得當前已登入使用者的詳細資訊。
    
    - **流程**: 從 JWT Token 中解析 `user_id` 並從資料庫快取中回傳。
    - **用途**: 用於前端初始化個人頁面。
    """
    return current_user

# 4. 修改密碼
@router.put("/me/password", summary="🔑 變更個人密碼")
async def change_password(
    data: MemberPasswordChange,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    """
    變更當前登入使用者的登入密碼。

    - **檢查項目**:
        - 必須提供正確的「舊密碼」進行驗證。
        - 新密碼長度需符合限制（3-50 字元）。
    - **後續影響**: 密碼變更後，下次登入需使用新密碼。
    """
    if not verify_password(data.current_password, current_user.password):
        raise HTTPException(status_code=400, detail="目前密碼輸入錯誤")

    current_user.password = get_password_hash(data.new_password)
    db.commit()
    return {"message": "密碼變更成功"}

# 5. 刪除個人帳號
@router.delete(
    "/me", summary="🗑️ 註銷帳號", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_my_account(
    db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)
):
    """
    永久刪除當前登入的帳號及其所有關聯數據。

    - **警告**: 此操作**不可逆**！
    - **關聯刪除**: 系統會同步刪除該用戶的：
        - 收支紀錄 (AddRecord)
        - 銀行/現金帳戶 (Account)
        - 交易明細 (Transaction)
        - 通知與回饋 (Notification, Feedback)
    """
    db.query(AddRecord).filter(AddRecord.user_id == current_user.user_id).delete()
    db.query(Account).filter(Account.user_id == current_user.user_id).delete()
    db.query(Transaction).filter(Transaction.user_id == current_user.user_id).delete()
    db.query(Notification).filter(Notification.user_id == current_user.user_id).delete()
    db.query(Feedback).filter(Feedback.user_id == current_user.user_id).delete()
    db.query(PasswordReset).filter(PasswordReset.user_id == current_user.user_id).delete()

    db.delete(current_user)
    db.commit()

    return None

# 6. 取得特定用戶資料 (為了解決前端獲取等級的問題)
@router.get("/{user_id}", response_model=MemberResponse, summary="🔍 取得特定用戶資料")
def get_member_by_id(
    user_id: int, 
    db: Session = Depends(get_db), 
    current_user: Member = Depends(get_current_user)
):
    """
    透過 user_id 取得用戶詳細資料，主要供前端主題系統判斷等級。
    """
    # 權限檢查：只能看自己，或是管理員可以看任何人
    if current_user.user_id != user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="權限不足")

    user = db.query(Member).filter(Member.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="找不到該使用者")
    
    return user
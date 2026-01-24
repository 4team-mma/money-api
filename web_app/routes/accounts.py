from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from ..schemas.accounts import AccountCreate, AccountResponse, AccountUpdate
from ..models import Account,Member
from ..database import get_db
from ..dependencies import get_current_user

# 注意：這裡不要加 prefix="/accounts"，因為 main.py 已經幫你加了
# tags 在 main.py 也有加，但這裡保留可以覆蓋或增加細節，不過通常建議這裡留空即可
router = APIRouter()

# ===== GET 所有帳戶 =====
# 網址對應: GET /api/accounts/
@router.get("/", response_model=List[AccountResponse])
def get_accounts(
    db: Session = Depends(get_db), 
    current_user: Member = Depends(get_current_user)
):
    return db.query(Account).filter(Account.user_id == current_user.user_id).all()


# ===== POST 新增帳戶 =====
# 網址對應: POST /api/accounts/
@router.post("/", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(
    account_in: AccountCreate, # 接收 Pydantic Schema
    db: Session = Depends(get_db), 
    current_user: Member = Depends(get_current_user)
):
    # 1. 將 Schema 轉為 Python 字典 (Pydantic v2 語法)
    account_data = account_in.model_dump()
    
    # 2. 補上 Schema 沒定義但在資料庫 Model 必須的欄位
    account_data["user_id"] = current_user.user_id
    
    # 邏輯：新開戶時，目前餘額 = 初始餘額
    account_data["current_balance"] = account_in.initial_balance 
    
    # 3. 建立資料庫物件 (自動解包: **account_data)
    # 這裡會自動把 account_name, account_icon, currency 等欄位填入
    new_account = Account(**account_data)

    try:
        db.add(new_account)
        db.commit()
        db.refresh(new_account) # 刷新以取得 DB 產生的 account_id
        return new_account
    except Exception as e:
        db.rollback()
        # 建議印出錯誤 log 方便除錯，這裡先簡單回傳 500
        raise HTTPException(status_code=500, detail=f"建立帳戶失敗: {str(e)}")
    
    
    
    
    
    # ===== DELETE 刪除帳戶 =====
# 網址對應: DELETE /api/accounts/{account_id}
@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    # 1. 尋找該帳戶，並同時檢查是否屬於該使用者 (安全性檢查)
    account_query = db.query(Account).filter(
        Account.account_id == account_id, 
        Account.user_id == current_user.user_id
    )
    
    account = account_query.first()

    # 2. 如果找不到，回傳 404
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="找不到該帳戶或無權限操作"
        )

    # 3. 執行刪除
    try:
        account_query.delete(synchronize_session=False)
        db.commit()
        # 204 No Content 不需要回傳 body
        return None
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"刪除帳戶失敗: {str(e)}"
        )
        
        
#更新尚未寫
@router.put("/{account_id}", response_model=AccountResponse)
def update_account(
    account_id: int, 
    obj_in: AccountUpdate, 
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    # 1. 🔍 必須同時確認 ID 和 User_ID (安全性)
    db_obj = db.query(Account).filter(
        Account.account_id == account_id, 
        Account.user_id == current_user.user_id
    ).first()

    if not db_obj:
        raise HTTPException(status_code=404, detail="找不到帳戶或無權限修改")

    # 2. 轉成字典，並排除前端沒傳過來的欄位 (避免把沒改的欄位蓋成 null)
    # Pydantic v2 用 model_dump(exclude_unset=True)
    update_data = obj_in.model_dump(exclude_unset=True)

    # 3. 執行更新邏輯
    try:
        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.add(db_obj) # 確保物件在 session 中
        db.commit()    # 🌟 核心：提交事務
        db.refresh(db_obj) # 刷新物件狀態
        return db_obj
    except Exception as e:
        db.rollback() # 出錯回滾
        print(f"Error during update: {e}")
        raise HTTPException(status_code=500, detail="資料庫更新失敗")
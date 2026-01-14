from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from ..schemas.accounts import AccountCreate, AccountResponse
from ..models import Account
from ..database import get_db
from ..dependencies import get_current_user_id

# 注意：這裡不要加 prefix="/accounts"，因為 main.py 已經幫你加了
# tags 在 main.py 也有加，但這裡保留可以覆蓋或增加細節，不過通常建議這裡留空即可
router = APIRouter()

# ===== GET 所有帳戶 =====
# 網址對應: GET /api/accounts/
@router.get("/", response_model=List[AccountResponse])
def get_accounts(
    db: Session = Depends(get_db), 
    user_id: int = Depends(get_current_user_id)
):
    return db.query(Account).filter(Account.user_id == user_id).all()


# ===== POST 新增帳戶 =====
# 網址對應: POST /api/accounts/
@router.post("/", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(
    account_in: AccountCreate, # 接收 Pydantic Schema
    db: Session = Depends(get_db), 
    user_id: int = Depends(get_current_user_id)
):
    # 1. 將 Schema 轉為 Python 字典 (Pydantic v2 語法)
    account_data = account_in.model_dump()
    
    # 2. 補上 Schema 沒定義但在資料庫 Model 必須的欄位
    account_data["user_id"] = user_id
    
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
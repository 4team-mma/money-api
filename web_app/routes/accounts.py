from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Account
# 假設您之後會建立 Schema，這裡先用基礎定義
from pydantic import BaseModel
from ..utils.jwt import verify_token
from fastapi.security import OAuth2PasswordBearer

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# 定義接收資料的結構
class AccountCreate(BaseModel):
    account_name: str
    icon_id: str
    account_type: str
    initial_balance: float
    exclude_from_assets: bool

# 定義 Token 提取依賴項
def get_current_user_id(token: str = Depends(oauth2_scheme)):
    payload = verify_token(token)
    return int(payload.get("sub"))

@router.get("/")
async def get_accounts(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id) # 自動從 Token 提取 ID
):
    #  根據 user_id 過濾，實現資料隔離
    return db.query(Account).filter(Account.user_id == user_id).all()

#  新增這個 POST 路由，解決 405 錯誤
@router.post("/")
async def create_account(
    data: AccountCreate, 
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    try:
        # 這裡暫時沒寫 user_id 驗證，正式環境需加入 Depends(get_current_user_id)
        new_acc = Account(
            user_id=user_id, #  使用動態 ID
            account_name=data.account_name,
            icon_id=data.icon_id,
            account_type=data.account_type,
            initial_balance=data.initial_balance,
            current_balance=data.initial_balance, # 初始時餘額等於初始餘額
            exclude_from_assets=data.exclude_from_assets,
            currency="TWD"
        )
        db.add(new_acc)
        db.commit()
        db.refresh(new_acc)
        return new_acc
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
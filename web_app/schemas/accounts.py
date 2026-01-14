from pydantic import BaseModel, ConfigDict
from decimal import Decimal
from typing import Optional

# 這是接收前端傳來資料的格式
class AccountCreate(BaseModel):
    account_name: str
    # 設定預設值，因為資料庫有 Default，但前端可能不傳
    account_type: str = "現金" 
    currency: str = "TWD"
    initial_balance: Decimal
    exclude_from_assets: bool = False
    
    # 修正：資料庫欄位是 account_icon，這裡必須同名才能自動對應
    # 如果前端介面選不到 icon，給一個預設值比較安全
    account_icon: str = "default_icon" 

# 這是回傳給前端的格式 (包含 ID 等資料庫生成的欄位)
class AccountResponse(AccountCreate):
    account_id: int
    user_id: int
    current_balance: Decimal

    # Pydantic v2 的設定寫法，允許從 ORM 物件讀取資料
    model_config = ConfigDict(from_attributes=True)
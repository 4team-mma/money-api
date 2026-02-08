from pydantic import BaseModel, ConfigDict, Field
from decimal import Decimal
from typing import Optional
from datetime import datetime


# 這是接收前端傳來資料的格式
class AccountCreate(BaseModel):
    account_name: str
    # 設定預設值，因為資料庫有 Default，但前端可能不傳
    account_type: str = "現金"
    currency: str = "NT$"
    initial_balance: float = Field(default=0.0)
    exclude_from_assets: bool = False

    # 修正：資料庫欄位是 account_icon，這裡必須同名才能自動對應
    # 如果前端介面選不到 icon，給一個預設值比較安全
    account_icon: str = "default_icon"


# 這是回傳給前端的格式 (包含 ID 等資料庫生成的欄位)
class AccountResponse(AccountCreate):
    account_id: int
    # user_id: int
    current_balance: float
    created_at: datetime  # 新增
    updated_at: datetime  # 新增

    # Pydantic v2 的設定寫法，允許從 ORM 物件讀取資料
    model_config = ConfigDict(from_attributes=True)


# 這是刪除成功時，如果你不想回傳空內容 (204)，可以回傳這個格式
class AccountDeleteResponse(BaseModel):
    message: str
    account_id: int


# 額外補充：這是「更新帳戶」用的 Schema
# 使用 Optional 讓前端可以只傳送「想修改」的欄位即可
class AccountUpdate(BaseModel):
    account_name: Optional[str] = None
    account_type: Optional[str] = None
    currency: Optional[str] = None
    initial_balance: Optional[Decimal] = None
    exclude_from_assets: Optional[bool] = None
    account_icon: Optional[str] = None

# 對應前端vue
# web_app/schemas/transfers.py
from pydantic import BaseModel, ConfigDict, Field
from datetime import date,datetime
from decimal import Decimal
from typing import Optional, List

class AccountInfo(BaseModel):
    account_id: int
    account_name: str = Field(..., description="帳戶名")
    account_icon: Optional[str]  = Field(None, description="帳戶圖示")
    currency: Optional[str] = Field(None, description="幣別")

# 單筆轉帳紀錄的詳細資料
class TransferDetail(BaseModel):
    transaction_id: int
    transaction_date: date = Field(..., description="日期")
    from_account_id: int = Field(..., description="來源帳戶id")
    to_account_id: int = Field(..., description="去向帳戶id")
    amount: Decimal = Field(..., description="金額")
    transaction_note: Optional[str] = Field(None, description="備註")
    
    # 關聯查詢後的額外欄位
    from_account: AccountInfo
    to_account: AccountInfo
    
    # 💡 這裡改成 Optional 且預設為 None
    created_at: Optional[datetime] = Field(None, description="建立時間")
    updated_at: Optional[datetime] = Field(None, description="更新時間")
    # Pydantic v2 的設定寫法，允許從 ORM 物件讀取資料
    model_config = ConfigDict(from_attributes=True)

# 月度轉帳列表的回應模型
class MonthlyTransferResponse(BaseModel):
    success: bool
    year: int
    month: int
    total_count: int
    data: List[TransferDetail] = Field(..., description="詳細轉帳紀錄清單")

    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra = {
            "example": {
                "success": True,
                "year": 2023,
                "month": 10,
                "total_count": 1,
                "total_transfer_amount": 5000.0,
                "data": [
                    {
                        "transaction_id": 101,
                        "transaction_date": "2023-10-15",
                        "from_account_id": 1,
                        "to_account_id": 2,
                        "amount": 5000.0,
                        "transaction_note": "薪資轉儲蓄",
                        "from_account_name": "國泰世華",
                        "from_account_icon": "🏦",
                        "from_currency": "NT$",
                        "to_account_name": "中信儲蓄"
                    }
                ]
            }
        })

# 請求 (Request): 是 Vue 前端發給 FastAPI 的「申請書」,資料還沒產生,所以不用id
class TransferCreate(BaseModel):
    transaction_date: date
    from_account_id: int  # 來源帳戶 ID
    to_account_id: int    # 目標帳戶 ID
    from_account_name: Optional[str] = None
    to_account_name: Optional[str] = None
    transaction_note: str | None = Field(
        None, 
        description="轉帳說明", 
        max_length=200)
    amount: Decimal
    
    

# 回應 (Response):
# 回應給前端的欄位，看你需要哪些開哪些
# 然後會繼承TransferCreate欄位
class TransferResponse(TransferCreate):
    transaction_id: int
    created_at: datetime # 新增
    updated_at: datetime # 新增
    #user_id: int
    from_account_id: int  # ✅ 這裡有定義

    # 使用from_attributes=True
    # 因為Pydantic只認字典，物件時會抱錯，使用這個=True是讓他能自動判斷轉換
    # 去讀它的屬性（Attributes）來填充資料
    model_config = ConfigDict(from_attributes=True)

# 修改 # 要與前端的transferPayload一致
# 因為帳戶有轉出轉入,就不需要單一的accountid
# 型別以前端的型別要一致,不是看資料庫的型別。例如from_account_id是對應account_id所以是int
# MySQL的from_accout是 (VARCHAR) 是用來存 最終的文字結果
class TransferUpdate(BaseModel):
    transaction_date: Optional[date] = None
    from_account_id:Optional[int] = None
    to_account_id:Optional[int] =None
    transaction_note: str | None = Field(
        None, 
        description="轉帳說明", 
        max_length=200)
    amount:Optional[Decimal]=None
    
    
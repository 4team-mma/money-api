# 對應前端vue
# web_app/schemas/transfers.py
from pydantic import BaseModel, ConfigDict
from datetime import date
from decimal import Decimal
from typing import Optional


# 請求 (Request): 是 Vue 前端發給 FastAPI 的「申請書」,資料還沒產生,所以不用id
class TransferCreate(BaseModel):
    transaction_date: date
    from_account_id: int  # 來源帳戶 ID
    to_account_id: int    # 目標帳戶 ID
    amount: Decimal
    

# 回應 (Response):
# 回應給前端的欄位，看你需要哪些開哪些
# 然後會繼承TransferCreate欄位
class TransferResponse(TransferCreate):
    transaction_id: int
    user_id: int
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
    amount:Optional[Decimal]=None
    
    
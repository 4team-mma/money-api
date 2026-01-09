from pydantic import BaseModel, ConfigDict # ConfigDict是將資料庫物件轉成Json
from datetime import date
from decimal import Decimal # 處理收支紀錄運算
from typing import Optional

# 前端點擊「儲存」時傳給後端的資料。不包含 id跟userid
class AddRecordCreate(BaseModel):
    add_date: date
    add_amount: Decimal
    add_type: bool
    add_class: str
    add_class_icon: str
    account_id: int
    add_member: str
    add_tag: Optional[str] = None
    add_note: Optional[str] = None

# 存檔成功後，回傳給前端顯示在清單上的資料。
class AddRecordResponse(AddRecordCreate):
    add_id: int
    user_id: int
    model_config = ConfigDict(from_attributes=True)

# 修改
class AddRecordUpdate(BaseModel):
    add_date: Optional[date] = None
    add_amount: Optional[Decimal] = None
    add_type: Optional[bool] = None
    add_class: Optional[str] = None
    add_class_icon: Optional[str] = None
    account_id: Optional[int] = None # 可能會換帳戶扣錢
    add_member: Optional[str] = None
    add_tag: Optional[str] = None
    add_note: Optional[str] = None
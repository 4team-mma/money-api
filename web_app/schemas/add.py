from pydantic import BaseModel, ConfigDict
from datetime import date
from decimal import Decimal # 💡 Pydantic 可以直接用 Decimal，沒問題
from typing import Optional

# 💡 確保有這個類別
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

# 💡 確保有這個類別
class AddRecordResponse(AddRecordCreate):
    id: int
    user_id: int

    model_config = ConfigDict(from_attributes=True)
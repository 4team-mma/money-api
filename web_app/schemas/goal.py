from pydantic import BaseModel
from decimal import Decimal
from datetime import date
from typing import Optional

class SavingsUpdate(BaseModel):
    goal_id: Optional[int] = None
    account_id: Optional[int] = None
    goal_name: str
    target_amount: Decimal
    current_amount: Decimal = Decimal("0.0")
    target_date: Optional[date] = None
    status: str = "active"

    class Config:
        from_attributes = True

from pydantic import BaseModel
from typing import Optional
from decimal import Decimal

class BudgetUpdate(BaseModel):
    amount: Decimal
    category: Optional[str] = None
    category_icon: Optional[str] = None
    tag: Optional[str] = None
    tag_color: Optional[str] = None
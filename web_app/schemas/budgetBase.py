from pydantic import BaseModel
from typing import Optional

class BudgetUpdate(BaseModel):
    amount: float
    category: Optional[str] = None
    category_icon: Optional[str] = None
    tag: Optional[str] = None
    tag_color: Optional[str] = None
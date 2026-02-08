# web_app/schemas/expenses.py
from pydantic import BaseModel, Field, RootModel
from typing import List

class ExpenseStatItem(BaseModel):
    id: int = Field(..., description="排序序號", examples=[1])
    category: str = Field(..., description="分組名稱", examples=["餐飲支出"])
    amount: float = Field(..., description="該組總金額", examples=[1500.5])
    ratio: float = Field(..., description="佔比百分比 (%)", examples=[45.5])

# ✅ Pydantic V2 正確的 Root Model 寫法
class ExpenseCategoryResponse(RootModel):
    root: List[ExpenseStatItem]
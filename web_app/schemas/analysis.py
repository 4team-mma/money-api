from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal
from typing import List, Optional
from datetime import datetime


# --- 薪資基準資料的回傳格式 ---
class SalaryBenchmarkResponse(BaseModel):
    salary_id: int
    industry: str = Field(..., description="行業別")
    period: str = Field(..., description="資料週期，例如 2025M12")
    salary_type: str = Field(..., description="經常性薪資 或 總薪資")
    salary_is_real: int = Field(..., description="0: 名目, 1: 實質")
    salary_val: Decimal = Field(..., description="薪資金額")

    #
    created_at: datetime = Field(..., description="建立時間")
    updated_at: datetime = Field(..., description="最後更新時間")

    model_config = ConfigDict(from_attributes=True)

# web_app/schemas/analysis.py
from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal
from typing import List, Optional
from datetime import datetime

class SalaryBenchmarkResponse(BaseModel):
    salary_id: int = Field(..., examples=[45])
    industry: str = Field(..., description="行業別", examples=["製造業"])
    period: str = Field(..., description="資料週期", examples=["2025M12"])
    salary_type: str = Field(..., description="薪資類型", examples=["總薪資"])
    salary_is_real: int = Field(..., description="0: 名目, 1: 實質", examples=[0])
    salary_val: Decimal = Field(..., description="薪資金額", examples=[58500.00])

    created_at: datetime = Field(..., description="建立時間")
    updated_at: datetime = Field(..., description="最後更新時間")

    model_config = ConfigDict(from_attributes=True)

# 提示：你也可以建立 CpiComparisonResponse 模型來讓第一個 API 更有規範
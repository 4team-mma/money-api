from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal
from datetime import date
from typing import Optional

class SavingsGoalBase(BaseModel):
    """儲蓄目標基礎欄位"""
    goal_name: str = Field(..., min_length=1, max_length=50, description="目標名稱", examples=["購置新筆電"])
    target_amount: Decimal = Field(..., ge=0, description="目標達標金額", examples=[50000.00])
    account_id: Optional[int] = Field(None, description="關聯帳戶 ID (若有則會自動同步餘額)", examples=[1])
    target_date: Optional[date] = Field(None, description="預計達成日期", examples=["2024-12-31"])
    status: str = Field("active", description="狀態: active (進行中), completed (已達成), failed (過期未達成)", examples=["active"])

class SavingsUpdate(SavingsGoalBase):
    """用於批次同步 (新增/更新) 的資料結構"""
    goal_id: Optional[int] = Field(None, description="目標 ID (新增時為 null，更新時必填)", examples=[123])
    current_amount: Optional[Decimal] = Field(Decimal("0.0"), description="目前儲蓄進度金額")

class SavingsGoalResponse(SavingsGoalBase):
    """用於 API 回傳的資料結構"""
    goal_id: int = Field(..., description="資料庫內唯一識別 ID")
    current_amount: Decimal = Field(..., description="目前進度 (可能根據帳戶餘額動態計算)")
    start_date: date = Field(..., description="目標創建日期")

    # 允許 Pydantic 讀取 SQLAlchemy ORM 物件
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "goal_id": 1,
                "goal_name": "買房基金",
                "target_amount": 2000000.0,
                "current_amount": 500000.0,
                "account_id": 5,
                "target_date": "2030-01-01",
                "start_date": "2023-10-01",
                "status": "active"
            }
        }
    )
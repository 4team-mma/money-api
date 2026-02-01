from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal


class AccountBrief(BaseModel):
    account_id: int
    account_name: str
    account_icon: Optional[str] = None
    current_balance: Decimal
    currency: str
    # 擴展資訊
    usage_count: Optional[int] = 0

    class Config:
        from_attributes = True


class DashboardResponse(BaseModel):
    highest_balance: List[AccountBrief]  # 餘額最高 Top 3
    recently_updated: List[AccountBrief]  # 最近變動 Top 3
    most_frequent: List[AccountBrief]  # 使用頻繁 Top 3

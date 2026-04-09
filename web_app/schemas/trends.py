from pydantic import BaseModel
from typing import List

class NetWorthItem(BaseModel):
    id: str
    date: str
    period: str
    net: float
    diff: float

class NetWorthHistoryResponse(BaseModel):
    daily: List[NetWorthItem]
    monthly: List[NetWorthItem]
    yearly: List[NetWorthItem]

from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class CardDisplay(BaseModel):
    lib_id: int
    title: str
    type: str # CARD or ACHIEVEMENT
    difficulty: str
    category: str  # 🌟 必須加入此欄位 (NT, SJ, SP, NF)
    series_name: Optional[str]
    image_url: Optional[str]
    is_owned: bool
    is_hidden: bool
    description: Optional[str]
    current_val: int
    target_val: int

    class Config:
        from_attributes = True

class SeriesStatus(BaseModel):
    series_name: str
    total_cards: int
    owned_cards: int
    is_completed: bool
    reward_feature: Optional[str]

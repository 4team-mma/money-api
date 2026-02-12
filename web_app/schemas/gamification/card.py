from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class CardDisplay(BaseModel):
    lib_id: int
    title: str
    type: str # CARD or ACHIEVEMENT
    series_name: Optional[str]
    image_url: Optional[str]
    is_owned: bool
    is_hidden: bool
    description: Optional[str]
    current_val: int # 針對成就進度
    target_val: int
    
    class Config:
        from_attributes = True

class SeriesStatus(BaseModel):
    series_name: str
    total_cards: int
    owned_cards: int
    is_completed: bool
    reward_feature: Optional[str]
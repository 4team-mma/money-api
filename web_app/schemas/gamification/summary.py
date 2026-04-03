from pydantic import BaseModel
from typing import Optional

class GameSummary(BaseModel):
    level: int
    xp: int
    next_level_xp: int  # 🌟 新增此欄位
    streak_count: int
    has_checked_in: bool
    username: Optional[str] = None
    job: Optional[str] = None
    points: int = 0
    max_level: int = 100

    class Config:
        from_attributes = True

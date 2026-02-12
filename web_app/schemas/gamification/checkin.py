from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional

class CheckinResponse(BaseModel):
    streak_count: int
    total_checkins: int
    earned_xp: int
    is_checked_in_today: bool
    checkin_date: date

    class Config:
        from_attributes = True

class CheckinStatus(BaseModel):
    has_checked_in: bool
    streak: int
    today_xp_reward: int # 預覽今天打卡能拿多少
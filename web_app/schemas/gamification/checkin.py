from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional

class CheckinResponse(BaseModel):
    streak_count: int
    cycle_day: int          # 新增：告訴前端現在是 1~7 的哪一天
    total_checkins: int
    earned_xp: int
    is_checked_in_today: bool
    show_bonus_modal: bool    # 新增：是否觸發滿 10 次獎勵視窗
    show_monthly_bonus: bool  # 新增：是否觸發月全勤獎勵視窗
    checkin_date: date

    class Config:
        from_attributes = True

class CheckinStatus(BaseModel):
    has_checked_in: bool
    current_cycle_day: int   # 修改：明確代表 1~7 循環中的位置
    today_xp_reward: int     # 預覽今天打卡能拿多少 (沒簽領取數，簽過顯示 0)
    weekly_rewards: list[int] # 固定回傳 [10, 10, 20, 20, 20, 20, 50]

    class Config:
        from_attributes = True

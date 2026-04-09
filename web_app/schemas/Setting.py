from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime

# 基礎設定 Schema
class SettingBase(BaseModel):
    budget_cycle: str = "monthly"
    budget_alert_threshold: int = 75
    start_of_week: int = 0
    app_theme: str = "light"
    admin_theme: str = "mma_light"
    avatar_url: Optional[str] = None
    birthday: Optional[date] = None
    about: Optional[str] = None

    class Config:
        from_attributes = True

# 更新主題專用的 Schema (用於 changeTheme)
class ThemeUpdate(BaseModel):
    app_theme: str = Field(..., example="dark")

# 回傳給前端的完整設定資料
class SettingRead(SettingBase):
    setting_id: int
    user_id: int
    updated_at: Optional[datetime] = None

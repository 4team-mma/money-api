from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator
from datetime import date, timedelta, datetime
from typing import Optional


class RepeatCycle(str, Enum):
    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


# 前端點擊「儲存」時傳給後端的資料。不包含 id 跟 userid
class NotificationCreate(BaseModel):
    reminder_title: str
    reminder_date_start: date
    reminder_date_end: date
    reminder_time: timedelta  # 儲存時使用 timedelta 型別
    repeat_cycle: RepeatCycle  # 使用 Enum 限制範圍
    description: Optional[str] = None

    # 邏輯檢查（結束日期不能早於開始日期）
    @field_validator("reminder_date_end")
    @classmethod
    def check_date_range(cls, v, info):
        if (
            v
            and "reminder_date_start" in info.data
            and info.data["reminder_date_start"]
        ):
            if v < info.data["reminder_date_start"]:
                raise ValueError("結束日期不可早於開始日期")
        return v


# 存檔成功後，回傳給前端顯示在清單上的資料。
class NotificationResponse(BaseModel):
    reminder_id: int
    # user_id: int
    reminder_title: str
    reminder_date_start: date
    reminder_date_end: date
    # 這是實際從資料庫讀取的欄位。使用 Field 設定 exclude=True 隱藏它。
    # Pydantic v2 使用 exclude=True 標記在序列化時排除此字段。
    raw_reminder_time: timedelta = Field(
        ..., exclude=True, validation_alias="reminder_time"
    )
    repeat_cycle: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @computed_field(alias="reminder_time")
    @property
    def reminder_time_formatted(self) -> str:
        """將 timedelta 轉換為 HH:MM:SS 格式的字串"""
        total_seconds = int(self.raw_reminder_time.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        # 確保格式為兩位數，例如 08:30:05
        return f"{hours:02}:{minutes:02}:{seconds:02}"


# 修改
class NotificationUpdate(BaseModel):
    reminder_title: Optional[str] = Field(None, min_length=1, max_length=20)
    reminder_date_start: Optional[date] = None
    reminder_date_end: Optional[date] = None
    reminder_time: Optional[timedelta] = None
    repeat_cycle: Optional[RepeatCycle] = None  # 使用 Enum 限制範圍
    description: Optional[str] = None

    # 邏輯檢查（結束日期不能早於開始日期）
    @field_validator("reminder_date_end")
    @classmethod
    def check_date_range(cls, v, info):
        if (
            v
            and "reminder_date_start" in info.data
            and info.data["reminder_date_start"]
        ):
            if v < info.data["reminder_date_start"]:
                raise ValueError("結束日期不可早於開始日期")
        return v

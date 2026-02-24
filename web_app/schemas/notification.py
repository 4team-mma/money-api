from pydantic import BaseModel, Field
from datetime import date, time
from typing import Optional

class NotificationCreate(BaseModel):
    reminder_title: str = Field(
        description="提醒標題", 
        min_length=1, 
        max_length=100
    )
    
    reminder_date_start: date = Field(
        description="提醒日期"
    )
    
    reminder_time: Optional[time] = Field(
        default=None, 
        description="提醒時間"
    )
    
    description: Optional[str] = Field(
        default=None, 
        max_length=500, 
        description="詳細描述"
    )

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "reminder_title": "繳交房租",
                "reminder_date_start": "2026-02-24",
                "reminder_time": "10:00:00",
                "description": "記得匯款給房東 $15,000"
            }
        }
    }

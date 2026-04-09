from pydantic import BaseModel
from datetime import datetime
from typing import List

class LoginActivityRead(BaseModel):
    activity_id: int
    ip_address: str
    device_info: str
    browser: str
    location: str
    login_at: datetime
    is_current: bool

    class Config:
        from_attributes = True

# 封裝成一個列表回傳
class AccountSecurityInfo(BaseModel):
    recent_logins: List[LoginActivityRead]

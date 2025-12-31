from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator

# --- 註冊頁面用的規格 ---
class MemberRegister(BaseModel):
    username: str = Field(min_length=1, max_length=50, description="暱稱")
    email: EmailStr = Field(description="電子郵件")
    password: str = Field(min_length=8, description="密碼，至少 8 字元")
    confirm_password: str = Field(description="確認密碼")

    # 💡 驗證：兩次密碼必須一樣
    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info):
        if 'password' in info.data and v != info.data['password']:
            raise ValueError("兩次輸入的密碼不一致")
        return v

# --- 登入頁面用的規格 ---
class MemberLogin(BaseModel):
    email: EmailStr = Field(description="電子郵件")
    password: str = Field(description="密碼")
    remember_me: bool = Field(default=False)

# --- 回傳給前端用的規格 (不含密碼) ---
class MemberResponse(BaseModel):
    user_id: int
    email: str
    username: str
    role: str
    xp: int = 0
    level: int = 1
    points: int = 0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
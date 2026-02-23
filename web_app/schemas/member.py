# web_app/schemas/member.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict

# --- 註冊頁面用的規格 ---
class MemberRegister(BaseModel):
    username: str = Field(
        ..., min_length=1, max_length=50, description="帳號", examples=["user123"]
    )
    name: str = Field(
        ..., min_length=1, max_length=50, description="顯示暱稱", examples=["小明"]
    )
    email: EmailStr = Field(
        ..., description="電子郵件", examples=["user@example.com"]
    )
    password: str = Field(
        ..., min_length=3, max_length=50, description="密碼", examples=["password123"]
    )
    confirm_password: str = Field(
        ..., description="確認密碼", examples=["password123"]
    )

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info):
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("兩次輸入的密碼不一致")
        return v

# --- 登入頁面用的規格 ---
class MemberLogin(BaseModel):
    identifier: str = Field(
        ..., description="電子郵件或帳號", examples=["user@example.com"]
    )
    password: str = Field(
        ..., description="密碼", examples=["mypassword123"]
    )
    remember_me: bool = Field(
        default=False, description="保持登入狀態 (True: 30天, False: 1小時)", examples=[True]
    )

# --- 修改個人資料規格 ---
class MemberUpdate(BaseModel):
    username: Optional[str] = Field(None, description="新帳號名稱", examples=["new_username"])
    name: Optional[str] = Field(None, description="新暱稱", examples=["新暱稱"])
    email: Optional[EmailStr] = Field(None, description="新電子郵件", examples=["new_email@example.com"])
    job: Optional[str] = Field(None, description="職稱", examples=["全端工程師"])

# --- 回傳給前端用的規格 ---
class MemberResponse(BaseModel):
    user_id: int = Field(..., description="使用者唯一識別碼", examples=[1])
    email: str = Field(..., examples=["user@example.com"])
    username: str = Field(..., examples=["user123"])
    name: str = Field(..., examples=["小明"])
    role: str = Field(..., examples=["user"])
    job: Optional[str] = Field(None, description="職稱", examples=["一般用戶"])
    xp: int = Field(0, examples=[100])
    level: int = Field(1, examples=[5])
    points: int = Field(0, examples=[500])
    created_at: Optional[datetime] = Field(None, examples=["2026-02-08T14:59:56.021Z"])

    model_config = ConfigDict(from_attributes=True)

# --- 變更密碼規格 ---
class MemberPasswordChange(BaseModel):
    current_password: str = Field(
        ..., description="目前密碼", examples=["old_password123"]
    )
    new_password: str = Field(
        ..., min_length=3, max_length=50, description="新密碼", examples=["new_secure_pass"]
    )
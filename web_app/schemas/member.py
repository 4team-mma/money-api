from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator,ConfigDict

# --- 註冊頁面用的規格 ---
class MemberRegister(BaseModel):
    username: str = Field(min_length=1, max_length=50, description="帳號",json_schema_extra={"example":"user"})
    name: str = Field(min_length=1, max_length=50, description="顯示暱稱",json_schema_extra={"example":"天黑請閉眼"})
    email: EmailStr = Field(description="電子郵件" , json_schema_extra={"example":"example@gmail.com"})
    password: str = Field(min_length=3, max_length=50,description="密碼，至少 3 字元,最多50字元",json_schema_extra={"example":"12345678"})
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
    identifier: str = Field(description="電子郵件或帳號",
                            json_schema_extra={"example": "user@example.com"}
                            )
    password: str = Field(description="密碼",
                            json_schema_extra={"example": "mypassword123"})
    remember_me: bool = Field(default=False,description="是否",
                            json_schema_extra={"example":"False"})
    
    
    
# ====修改
class MemberUpdate(BaseModel):
    username: Optional[str] = None
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    job: Optional[str] = None #  允許修改職稱

# --- 回傳給前端用的規格 (不含密碼) ---
class MemberResponse(BaseModel):
    #user_id: int
    email: str
    username: str
    name: str
    role: str
    job: Optional[str] = None
    xp: int = 0
    level: int = 1
    points: int = 0
    created_at: Optional[datetime] = None
    
    #Pydantic v2 建議統一使用
    model_config = ConfigDict(from_attributes=True)
        
# 刪除      
class MemberDeleteResponse(BaseModel):
    message: str
    #user_id: int

# 用於變更密碼的規格
class MemberPasswordChange(BaseModel):
    current_password: str = Field(description="目前密碼",json_schema_extra={"example":"12345678"})
    new_password: str = Field(min_length=3, max_length=50, description="新密碼")
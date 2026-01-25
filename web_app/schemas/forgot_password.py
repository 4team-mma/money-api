from pydantic import BaseModel, EmailStr, Field

# 步驟 1：發送驗證碼的請求
class SendOTPRequest(BaseModel):
    email: EmailStr = Field(..., description="使用者的電子郵件")
    recaptcha_token: str = Field(..., description="Google reCAPTCHA 驗證權杖")

# 步驟 2：驗證驗證碼是否正確
class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6, description="6 位數驗證碼")

# 步驟 3：正式修改密碼
class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    new_password: str = Field(..., min_length=3, max_length=50, description="新密碼，至少 3 位元,最大50位元")
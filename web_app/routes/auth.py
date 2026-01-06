from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from ..database import get_db
from ..models import Member, PasswordReset  # 💡 確保導入了這兩個模型
from ..schemas.member import MemberRegister, MemberLogin
# 💡 導入我們之前建立的 Schema 與工具
from ..schemas.forgot_password import SendOTPRequest, VerifyOTPRequest, ResetPasswordRequest
from ..utils.otp import generate_otp
from ..utils.email_utils import send_otp_email
from ..utils.password import hash_password, verify_password
from ..utils.jwt import create_access_token

router = APIRouter()

# ==================== 守門員與權限 ====================

async def admin_required():
    """管理員權限驗證依賴項 (預留未來檢查邏輯)"""
    return True

# ==================== 註冊與登入 ====================

@router.post("/auth/register")
async def register(data: MemberRegister, db: Session = Depends(get_db)):
    # 檢查 Email 是否已被註冊
    existing_user = db.query(Member).filter(Member.email == data.email).first()
    if existing_user:
    
        raise HTTPException(status_code=400, detail="此電子郵件已被註冊")

    # 建立新會員 (記得加密密碼)
    new_user = Member(
        username=data.username,
        name=data.name,
        email=data.email,
        password=hash_password(data.password),
        role="user"
    )
    db.add(new_user)
    db.commit()
    return {"msg": "註冊成功"}

@router.post("/auth/login")
async def login(data: MemberLogin, db: Session = Depends(get_db)):
    # 🌟 1. 先從資料庫找人
    user = db.query(Member).filter(
        (Member.username == data.identifier) | (Member.email == data.identifier)
    ).first()
    
    if not user:
        print(f"❌ 找不到使用者: {data.identifier}")
        raise HTTPException(status_code=401, detail="帳號不存在或輸入錯誤")

    # 🌟 2. 找到人後，才進行密碼比對並列印日誌
    is_correct = verify_password(data.password, user.password)
    print(f"🔍 比對密碼: 輸入={data.password}, 資料庫雜湊碼={user.password}, 結果={is_correct}")
    
    if not is_correct:
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")
    
    # 🌟 3. 驗證通過，建立 Token
    access_token = create_access_token(data={"sub": str(user.user_id)})
    
    return {
        "msg": "登入成功",
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email,
            "role": user.role
        }
    }

# ==================== 忘記密碼邏輯 (新增) ====================

@router.post("/auth/forgot-password/send-otp")
async def send_otp(data: SendOTPRequest, db: Session = Depends(get_db)):
    """步驟 1: 發送驗證碼到信箱"""
    # 1. 檢查使用者是否存在
    user = db.query(Member).filter(Member.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="此信箱尚未註冊為會員")

    # 2. 產生 6 位數驗證碼與 5 分鐘後的過期時間
    otp = generate_otp()
    expiry = datetime.now() + timedelta(minutes=5)

    # 3. 寫入 password_resets 表格
    new_reset_entry = PasswordReset(
        user_id=user.user_id,
        email=user.email,
        otp_code=otp,
        expires_at=expiry
    )
    db.add(new_reset_entry)
    db.commit()

    # 4. 真正發送郵件
    email_success = send_otp_email(user.email, otp)
    if not email_success:
        raise HTTPException(status_code=500, detail="驗證信發送失敗，請稍後再試")

    return {"msg": "驗證碼已寄出，請檢查您的信箱"}

@router.post("/auth/forgot-password/verify-otp")
async def verify_otp(data: VerifyOTPRequest, db: Session = Depends(get_db)):
    """步驟 2: 驗證前端輸入的 Code 是否正確且有效"""
    # 查詢最新的一筆、未被使用過且未過期的紀錄
    record = db.query(PasswordReset).filter(
        PasswordReset.email == data.email,
        PasswordReset.otp_code == data.otp,
        PasswordReset.is_used == False,
        PasswordReset.expires_at > datetime.now()
    ).order_by(PasswordReset.created_at.desc()).first()

    if not record:
        raise HTTPException(status_code=400, detail="驗證碼錯誤或已過期")
    
    return {"msg": "驗證通過，請重新設定新密碼"}

@router.post("/auth/forgot-password/reset")
async def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    """步驟 3: 正式更新資料庫密碼"""
    # 再次確認驗證碼紀錄有效性 (防止駭客直接呼叫此 API)
    record = db.query(PasswordReset).filter(
        PasswordReset.email == data.email,
        PasswordReset.otp_code == data.otp,
        PasswordReset.is_used == False
    ).first()

    if not record:
        raise HTTPException(status_code=400, detail="請求無效，請重新進行驗證流程")

    # 1. 更新 Member 表的密碼
    user = db.query(Member).filter(Member.email == data.email).first()
    if user is None:
        # 理論上 record 存在則 user 應存在，但為了程式健壯性與消除警告，必須檢查
        raise HTTPException(status_code=404, detail="找不到該使用者，無法重設密碼")
    user.password = hash_password(data.new_password)
    
    # 2. 將驗證碼設為已使用
    record.is_used = True
    
    db.commit()
    return {"msg": "密碼已成功修改！"}
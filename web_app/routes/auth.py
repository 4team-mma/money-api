from fastapi import APIRouter, Depends, HTTPException, status,Request, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import desc # 用於排序找出最後一筆 OTP 紀錄
from datetime import datetime, timedelta
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordRequestForm
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from ..database import get_db
from ..models import Member, PasswordReset, Account
from ..schemas.member import MemberRegister, MemberLogin
from ..schemas.forgot_password import SendOTPRequest, VerifyOTPRequest, ResetPasswordRequest
from ..utils.otp import generate_otp
from ..utils.email_utils import send_otp_email
from ..utils.password import get_password_hash, verify_password
from ..utils.jwt import create_access_token
import uuid
from slowapi import Limiter
from slowapi.util import get_remote_address
from ..utils.email_utils import verify_recaptcha, send_otp_email 
import os


router = APIRouter()

# ==================== 守門員與權限 ====================
# 此部分在dependencies的admin_required




# =======IP 限制、reCAPTCHA、每日上限與非同步寄信功能============
# 1. 初始化 IP 限制器 (每分鐘同一個 IP 只能請求 5 次)
limiter = Limiter(key_func=get_remote_address)

@router.post("/auth/forgot-password/send-otp")
@limiter.limit("5/minute") # 第一層：IP 限制 (slowapi)
async def request_password_reset_otp(
    # pylint: disable=unused-argument
    request: Request, # slowapi 必須要有這個參數
    data: SendOTPRequest, 
    background_tasks: BackgroundTasks, # 異步寄信專用
    db: Session = Depends(get_db)
):
    # --- 第二層：Google reCAPTCHA 驗證 ---
    # 假設你的 SendOTPRequest 有包含 recaptcha_token 欄位
    if not verify_recaptcha(data.recaptcha_token):
        raise HTTPException(status_code=400, detail="機器人驗證失敗，請重新嘗試")

    user = db.query(Member).filter(Member.email == data.email).first()
    if not user:
        # 資安策略：對外統一口徑，不透露使用者是否存在
        return {"msg": "若信箱正確，驗證碼已寄出"}

    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # --- 第三層：資料庫檢查 (每日上限 5 次) ---
    daily_count = db.query(PasswordReset).filter(
        PasswordReset.email == data.email,
        PasswordReset.created_at >= today_start
    ).count()

    if daily_count >= 5:
        raise HTTPException(status_code=429, detail="今日發送次數已達上限")

    # --- 第四層：60 秒冷卻時間 (你原本寫得很好的邏輯) ---
    last_otp = db.query(PasswordReset).filter(PasswordReset.email == data.email)\
                .order_by(desc(PasswordReset.created_at)).first()

    if last_otp and (now - last_otp.created_at).total_seconds() < 60:
        wait = int(60 - (now - last_otp.created_at).total_seconds())
        raise HTTPException(status_code=429, detail=f"請等待 {wait} 秒後再試")

    # --- 第五層：產碼、存檔與「非同步」寄信 ---
    otp = generate_otp()
    new_reset_entry = PasswordReset(
        user_id=user.user_id,
        email=user.email,
        otp_code=otp,
        expires_at=now + timedelta(minutes=5)
    )
    db.add(new_reset_entry)
    db.commit()

    # 使用 background_tasks，API 會立刻回應成功，後端才慢慢寄信
    background_tasks.add_task(send_otp_email, user.email, otp)

    return {"msg": "驗證碼已寄出，請檢查您的信箱"}

# ==========================================================

# ==================== 註冊與登入 ====================
@router.post("/auth/register")
async def register(data: MemberRegister, db: Session = Depends(get_db)):
    #  資安優化：同時檢查 Email 與 Username，並使用統一的錯誤訊息防止列舉攻擊
    user_exists = db.query(Member).filter(Member.username == data.username).first()
    email_exists = db.query(Member).filter(Member.email == data.email).first()
    
    if user_exists or email_exists:
        # 駭客無法得知是「帳號」還是「信箱」被用過
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="帳號或電子郵件已被使用，請嘗試其他名稱"
        )
    
    

    # 建立新會員 (記得加密密碼)
    new_user = Member(
        username=data.username,
        name=data.name,
        email=data.email,
        password=get_password_hash(data.password),
        role="user"
    )
    db.add(new_user)
    db.flush() # 🌟 使用 flush 先取得 new_user.user_id，但不提交 Transaction

    # 為新使用者建立預設帳戶
    # 若帳戶建立失敗，整筆註冊（含會員）應一起回滾，確保資料一致性
    default_accounts = [
        Account(
            user_id=new_user.user_id,
            account_type='現金',
            account_name='我的錢包',
            currency='NT$',
            initial_balance=0,
            current_balance=0,
            exclude_from_assets=False,
            account_icon='💰'
        ),
        Account(
            user_id=new_user.user_id,
            account_type='銀行',
            account_name='預設銀行',
            currency='NT$',
            initial_balance=0,
            current_balance=0,
            exclude_from_assets=False,
            account_icon='🏦'
        )
    ]
    db.add_all(default_accounts)
    
    # 統一提交
    db.commit()
    
    return {"msg": "註冊成功"}

@router.post("/auth/login")
async def login(data: MemberLogin, db: Session = Depends(get_db)):
    # 🌟 1. 先從資料庫找人
    user = db.query(Member).filter(
        (Member.username == data.identifier) | (Member.email == data.identifier)
    ).first()
    
    if not user or not verify_password(data.password, user.password):
        # 優化：統一報錯訊息，不告知是帳號錯還是密碼錯
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")
    
    access_token = create_access_token(data={"sub": str(user.user_id)})
    
    return {
        "msg": "登入成功",
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "name": user.name
        }
    }

# --- Google 登入相關 ---
class GoogleAuthRequest(BaseModel):
    token: str

# key寫在.env
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")

@router.post("/auth/google")
async def google_auth(data: GoogleAuthRequest, db: Session = Depends(get_db)):
    # 1. 驗證 Google Token (保持 ValueError 捕獲，因為這是特定的業務錯誤)
    try:
        id_info = id_token.verify_oauth2_token(
            data.token, 
            google_requests.Request(), 
            GOOGLE_CLIENT_ID
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Google Token 驗證無效")

    # 2. 取得 Google 使用者資訊
    email = id_info['email']
    full_name = id_info.get('name', 'Google 使用者')
    
    # 3. 檢查使用者是否已存在
    user = db.query(Member).filter(Member.email == email).first()

    # 4. 如果使用者不存在，執行「原子化」註冊流程
    if not user:
        # 生成不重複的預設帳號
        default_username = f"{email.split('@')[0]}_{datetime.now().strftime('%M%S')}"
        
        # 建立新會員
        new_user = Member(
            username=default_username,
            name=full_name,
            email=email,
            password=get_password_hash(str(uuid.uuid4())), # 隨機密碼
            role="user",
            status="active",
            created_at=datetime.now(),
            job="一般用戶"
        )
        db.add(new_user)
        db.flush() # 🌟 先取得 user_id，不提交事務

        # 🌟 為新用戶同步建立預設帳戶
        default_accounts = [
            Account(
                user_id=new_user.user_id,
                account_type='現金',
                account_name='我的錢包',
                currency='NT$',
                initial_balance=0,
                current_balance=0,
                exclude_from_assets=False,
                account_icon='💰'
            ),
            Account(
                user_id=new_user.user_id,
                account_type='銀行',
                account_name='預設銀行',
                currency='NT$',
                initial_balance=0,
                current_balance=0,
                exclude_from_assets=False,
                account_icon='🏦'
            )
        ]
        db.add_all(default_accounts)
        
        # 統一提交：確保「會員」與「帳戶」同時建立成功
        db.commit()
        db.refresh(new_user)
        user = new_user

    # 5. 簽發 JWT Token
    access_token = create_access_token(data={"sub": str(user.user_id)})
    
    return {
        "msg": "Google 登入成功",
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email,
            "name": user.name
        }
    }

# ==================== 忘記密碼邏輯 ====================

@router.post("/auth/forgot-password/send-otp")
async def send_otp(data: SendOTPRequest, db: Session = Depends(get_db)):
    user = db.query(Member).filter(Member.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="此信箱尚未註冊為會員")

    # 新增：60 秒發信冷卻時間邏輯
    last_otp = db.query(PasswordReset).filter(
        PasswordReset.email == data.email
    ).order_by(desc(PasswordReset.created_at)).first()

    if last_otp:
        # 計算距離上一次發信過了幾秒
        time_diff = (datetime.now() - last_otp.created_at).total_seconds()
        if time_diff < 60:
            raise HTTPException(
                status_code=429, 
                detail=f"請求過於頻繁，請於 {int(60 - time_diff)} 秒後再試"
            )

    otp = generate_otp()
    expiry = datetime.now() + timedelta(minutes=5)

    new_reset_entry = PasswordReset(
        user_id=user.user_id,
        email=user.email,
        otp_code=otp,
        expires_at=expiry
    )
    db.add(new_reset_entry)
    db.commit()

    email_success = send_otp_email(user.email, otp)
    if not email_success:
        raise HTTPException(status_code=500, detail="驗證信發送失敗，請稍後再試或聯繫客服")

    return {"msg": "驗證碼已寄出，請檢查您的信箱"}

@router.post("/auth/forgot-password/verify-otp")
async def verify_otp(data: VerifyOTPRequest, db: Session = Depends(get_db)):
    # 🌟 修正 Ruff E712：使用 .is_(False) 替代 == False
    record = db.query(PasswordReset).filter(
        PasswordReset.email == data.email,
        PasswordReset.otp_code == data.otp,
        PasswordReset.is_used.is_(False),
        PasswordReset.expires_at > datetime.now()
    ).order_by(PasswordReset.created_at.desc()).first()

    if not record:
        raise HTTPException(status_code=400, detail="驗證碼錯誤或已過期")
    
    return {"msg": "驗證通過，請重新設定新密碼"}

@router.post("/auth/forgot-password/reset")
async def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    # 🌟 修正 Ruff E712：使用 .is_(False) 替代 == False
    record = db.query(PasswordReset).filter(
        PasswordReset.email == data.email,
        PasswordReset.otp_code == data.otp,
        PasswordReset.is_used.is_(False)
    ).first()

    if not record:
        raise HTTPException(status_code=400, detail="請求無效，請重新進行驗證流程")

    user = db.query(Member).filter(Member.email == data.email).first()
    if user is None:
        raise HTTPException(status_code=404, detail="找不到該使用者，無法重設密碼")
    
    user.password = get_password_hash(data.new_password)
    record.is_used = True
    
    db.commit()
    return {"msg": "密碼已成功修改！"}

@router.post("/auth/token")
async def login_for_swagger(
    form_data: OAuth2PasswordRequestForm = Depends(), 
    db: Session = Depends(get_db)
):
    user = db.query(Member).filter(
        (Member.username == form_data.username) | (Member.email == form_data.username)
    ).first()
    
    if not user:
        raise HTTPException(status_code=401, detail="帳號不存在或輸入錯誤")

    if not verify_password(form_data.password, user.password):
        raise HTTPException(status_code=401, detail="密碼錯誤")
    
    access_token = create_access_token(data={"sub": str(user.user_id)})
    
    return {"access_token": access_token, "token_type": "bearer"}
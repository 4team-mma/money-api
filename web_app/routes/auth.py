from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
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
    db.refresh(new_user)

    # 🚀 自動化：為新使用者建立預設帳戶
    try:
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
        db.commit()
    except Exception as e:
        print(f"預設帳戶建立失敗: {e}")
        
    return {"msg": "註冊成功"}

@router.post("/auth/login")
async def login(data: MemberLogin, db: Session = Depends(get_db)):
    # 🌟 1. 先從資料庫找人
    user = db.query(Member).filter(
        (Member.username == data.identifier) | (Member.email == data.identifier)
    ).first()
    
    if not user:
        raise HTTPException(status_code=401, detail="帳號不存在或輸入錯誤")

    # 🌟 2. 找到人後，進行密碼比對
    if not verify_password(data.password, user.password):
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

# --- Google 登入相關 ---
class GoogleAuthRequest(BaseModel):
    token: str

GOOGLE_CLIENT_ID = "709149079121-1mma6vkj82ni707n86sp098ub1re4q22.apps.googleusercontent.com"

@router.post("/auth/google")
async def google_auth(data: GoogleAuthRequest, db: Session = Depends(get_db)):
    try:
        # 1. 驗證 Google Token (修正變數名稱以符合拼字檢查)
        id_info = id_token.verify_oauth2_token(
            data.token, 
            google_requests.Request(), 
            GOOGLE_CLIENT_ID
        )

        # 2. 取得 Google 使用者資訊
        email = id_info['email']
        full_name = id_info.get('name', 'Google 使用者')
        default_username = email.split('@')[0]

        # 3. 檢查資料庫是否有此 Email
        user = db.query(Member).filter(Member.email == email).first()

        # 4. 如果使用者不存在，自動幫他註冊
        if not user:
            placeholder_password = hash_password("OAUTH_USER_RANDOM_SECRET")
            
            new_user = Member(
                username=default_username,
                name=full_name,
                email=email,
                password=placeholder_password,
                role="user",
                status="active",
                created_at=datetime.now(),
                job="一般用戶"
            )
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            
            # 🌟 為 Google 新用戶建立預設帳戶
            try:
                default_accounts = [
                    Account(
                        user_id=new_user.user_id,
                        account_type='現金',
                        account_name='我的錢包',
                        currency='TWD',
                        initial_balance=0,
                        current_balance=0,
                        exclude_from_assets=False,
                        account_icon='💰'
                    ),
                    Account(
                        user_id=new_user.user_id,
                        account_type='銀行',
                        account_name='預設銀行',
                        currency='TWD',
                        initial_balance=0,
                        current_balance=0,
                        exclude_from_assets=False,
                        account_icon='🏦'
                    )
                ]
                db.add_all(default_accounts)
                db.commit()
            except Exception as e:
                print(f"Google 用戶預設帳戶建立失敗: {e}")
            
            user = new_user

        # 簽發 JWT Token
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

    except ValueError:
        raise HTTPException(status_code=400, detail="Google Token 驗證無效")
    except Exception as e:
        print(f"Google 認證流程錯誤: {e}")
        raise HTTPException(status_code=500, detail="伺服器處理 Google 登入時出錯")

# ==================== 忘記密碼邏輯 ====================

@router.post("/auth/forgot-password/send-otp")
async def send_otp(data: SendOTPRequest, db: Session = Depends(get_db)):
    user = db.query(Member).filter(Member.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="此信箱尚未註冊為會員")

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
        raise HTTPException(status_code=500, detail="驗證信發送失敗，請稍後再試")

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
    
    user.password = hash_password(data.new_password)
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
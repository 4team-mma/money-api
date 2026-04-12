from user_agents import parse # 用於解析裝置資訊
import httpx
from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import desc  # 用於排序找出最後一筆 OTP 紀錄
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from fastapi.security import OAuth2PasswordRequestForm
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from typing import Optional
from ..database import get_db
from ..models import PasswordReset, Account
from ..schemas.member import MemberRegister, MemberLogin
from ..schemas.forgot_password import (
    SendOTPRequest,
    VerifyOTPRequest,
    ResetPasswordRequest,
)
from ..utils.otp import generate_otp
from ..utils.email_utils import send_otp_email
from ..utils.password import get_password_hash, verify_password
from ..utils.jwt import create_access_token
import uuid
from slowapi import Limiter
from slowapi.util import get_remote_address
from ..utils.email_utils import verify_recaptcha, send_otp_email
import os
# ✨ 新增 Model 引入 (用來操作資料庫)
# 根據你的 models.py 內容，Member 和 Setting 都在這裡
from ..models.models import Member, Setting,LoginActivity


router = APIRouter()
# ==================== 守門員與權限 ====================
# 此部分在dependencies的admin_required

# =======IP 限制、reCAPTCHA、每日上限與非同步寄信功能============
# 1. 初始化 IP 限制器 (每分鐘同一個 IP 只能請求 5 次)
limiter = Limiter(key_func=get_remote_address)


# ==================== 忘記密碼邏輯 ====================
@router.post("/auth/forgot-password/send-otp", summary="🔑 OPT驗證碼發送")
@limiter.limit("5/minute")  # 第一層：IP 限制 (slowapi)
async def request_password_reset_otp(
    # pylint: disable=unused-argument
    request: Request,  # slowapi 必須要有這個參數
    data: SendOTPRequest,
    background_tasks: BackgroundTasks,  # 異步寄信專用
    db: Session = Depends(get_db),

):
    """
    發送 6 位數驗證碼，用於忘記密碼。具備多重資安防護機制。

    - **防護機制**:
        1. **IP 限制**: 同 IP 每分鐘限 5 次。
        2. **reCAPTCHA**: 必須通過 Google 機器人驗證。
        3. **每日上限**: 同一 Email 每天只能發送 5 次。
        4. **冷卻時間**: 每次發送需間隔 60 秒。

    - **資安注意**:
        - 無論 Email 是否存在，系統都會回傳「驗證碼已寄出」的成功訊息，以防止駭客掃描帳號。
        - 實際寄信為**背景執行** (Background Task)，API 回應速度快。
    """
    
    print(f"\n[DEBUG START] --- 收到發送驗證碼請求 ---")
    print(f"DEBUG: 目標 Email: {data.email}")
    
    # ---檢查debug：Google reCAPTCHA 驗證 ---
    print("DEBUG: 正在驗證 reCAPTCHA...")
    recaptcha_ok = verify_recaptcha(data.recaptcha_token)
    print(f"DEBUG: reCAPTCHA 驗證結果: {recaptcha_ok}")
    
    # --- 第二層：Google reCAPTCHA 驗證 ---
    # 假設你的 SendOTPRequest 有包含 recaptcha_token 欄位
    if not verify_recaptcha(data.recaptcha_token):
        raise HTTPException(status_code=400, detail="機器人驗證失敗，請重新嘗試")

    user = db.query(Member).filter(Member.email == data.email).first()
    if not user:
        # 資安策略：對外統一口徑，不透露使用者是否存在
        print(f"DEBUG: [WARN] 資料庫找不到此 Email: {data.email}")
        return {"msg": "若信箱正確，驗證碼已寄出"}

    print(f"DEBUG: 找到使用者 ID: {user.user_id}")
    
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # --- 第三層：資料庫檢查 (每日上限 5 次) ---
    daily_count = (
        db.query(PasswordReset)
        .filter(
            PasswordReset.email == data.email, PasswordReset.created_at >= today_start
        )
        .count()
    )

    print(f"DEBUG: 該 Email 今日已發送次數: {daily_count}")
    
    if daily_count >= 5:
        print("DEBUG: [FAIL] 已達每日上限")
        raise HTTPException(status_code=429, detail="今日發送次數已達上限")

    # --- 第四層：60 秒冷卻時間 (你原本寫得很好的邏輯) ---
    last_otp = (
        db.query(PasswordReset)
        .filter(PasswordReset.email == data.email)
        .order_by(desc(PasswordReset.created_at))
        .first()
    )

    if last_otp and (now - last_otp.created_at).total_seconds() < 60:
        wait = int(60 - (now - last_otp.created_at).total_seconds())
        print(f"DEBUG: [FAIL] 處於冷卻時間，需等待 {wait}s")
        raise HTTPException(status_code=429, detail=f"請等待 {wait} 秒後再試")

    # --- 第五層：產碼、存檔與「非同步」寄信 ---
    otp = generate_otp()
    print(f"DEBUG: 產生新 OTP: {otp}")
    new_reset_entry = PasswordReset(
        user_id=user.user_id,
        email=user.email,
        otp_code=otp,
        expires_at=now + timedelta(minutes=5),
    )
    db.add(new_reset_entry)
    db.commit()
    print("DEBUG: OTP 已成功寫入資料庫")
    # 使用 background_tasks，API 會立刻回應成功，後端才慢慢寄信
    background_tasks.add_task(send_otp_email, user.email, otp)


    print(f"DEBUG: [SUCCESS] 任務已掛載，準備回傳 API 成功訊息")
    print(f"[DEBUG END] ----------------------------\n")

    return {"msg": "驗證碼已寄出，請檢查您的信箱"}


# ==========================================================


# ==================== 註冊與登入 ====================
@router.post("/auth/register", summary="🙂 會員註冊")
async def register(data: MemberRegister, db: Session = Depends(get_db)):
    """
    建立新會員帳號，並同時初始化個人的資產帳戶。

    - **流程**:
        1. 檢查 Username 與 Email 是否重複 (回傳 400)。
        2. 建立會員資料 (密碼加密)。
        3. **自動建立帳戶**: 系統會自動為新用戶建立「我的錢包(現金)」與「預設銀行」兩個帳戶。

    - **錯誤處理**:
        - 若帳號重複，會回傳模糊的錯誤訊息「帳號或電子郵件已被使用」以防止列舉攻擊。
    """

    #  資安優化：同時檢查 Email 與 Username，並使用統一的錯誤訊息防止列舉攻擊
    user_exists = db.query(Member).filter(Member.username == data.username).first()
    email_exists = db.query(Member).filter(Member.email == data.email).first()

    if user_exists or email_exists:
        # 駭客無法得知是「帳號」還是「信箱」被用過
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="帳號或電子郵件已被使用，請嘗試其他名稱",
        )

    # 建立新會員 (記得加密密碼)
    new_user = Member(
        username=data.username,
        name=data.name,
        email=data.email,
        password=get_password_hash(data.password),
        role="user",
    )
    db.add(new_user)
    db.flush()  # 🌟 使用 flush 先取得 new_user.user_id，但不提交 Transaction

    # 為新使用者建立預設帳戶
    # 若帳戶建立失敗，整筆註冊（含會員）應一起回滾，確保資料一致性
    default_accounts = [
        Account(
            user_id=new_user.user_id,
            account_type="現金",
            account_name="我的錢包",
            currency="NT$",
            initial_balance=0,
            current_balance=0,
            exclude_from_assets=False,
            account_icon="💰",
        ),
        Account(
            user_id=new_user.user_id,
            account_type="銀行",
            account_name="預設銀行",
            currency="NT$",
            initial_balance=0,
            current_balance=0,
            exclude_from_assets=False,
            account_icon="🏦",
        ),
    ]
    db.add_all(default_accounts)

    # 統一提交
    db.commit()

    return {"msg": "註冊成功"}

@router.post("/auth/login", summary="🔐 會員登入")
@limiter.limit("5/minute")  # 🌟 加上這行，同 IP 每分鐘只能敲 5 次門
async def login(
    data: MemberLogin,
    request: Request,
    db: Session = Depends(get_db)):
    
    """
    一般會員登入接口。

    - **輸入**: `identifier` 欄位可接受 **Username** 或 **Email**。
    - **回傳**: JWT Access Token 與部分使用者資訊。
    - **錯誤**: 帳號或密碼錯誤統一回傳 401，不透露具體錯誤原因。
    - **remember_me**: `True`:保持登入狀態 30 天, `False`:1小時
    """

    # 1. 先從資料庫找人
    user = (
        db.query(Member)
        .filter(
            (Member.username == data.identifier) | (Member.email == data.identifier)
        )
        .first()
    )

    if not user:
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")

    # 登入邏輯
    if user.status == "banned":
        raise HTTPException(status_code=403, detail="您的帳號已被停用，請聯繫管理員。")

    # 2. 檢查是否正在鎖定期間
    if user.lockout_until and isinstance(user.lockout_until, datetime):
        if user.lockout_until > datetime.now():
            wait_time = int((user.lockout_until - datetime.now()).total_seconds() / 60)
            raise HTTPException(status_code=403, detail=f"嘗試次數過多，帳號已被鎖定，請於 {max(1, wait_time)} 分鐘後再試")

    # 3. 驗證密碼
    if not verify_password(data.password, user.password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= 5:
            user.lockout_until = datetime.now() + timedelta(minutes=15)
            db.commit()
            raise HTTPException(status_code=403, detail="嘗試次數過多，帳號已被暫時鎖定 15 分鐘")
        db.commit()
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")
    else:
        # 更新最後登入時間
        user.last_login = datetime.now()

    # 登入成功，重置失敗次數
    user.failed_login_attempts = 0

    # 登入成功，重置失敗次數
    user.failed_login_attempts = 0

    # 🌟 核心：如果有傳入 line_user_id，就寫入資料庫完成綁定
    if data.line_user_id:
        user.line_user_id = data.line_user_id

    # 把重置失敗次數跟 line_user_id 一起 commit 存檔
    db.commit()

    # 4. 處理「記住我」邏輯
    if data.remember_me:
        access_token_expires = timedelta(days=30)
    else:
        access_token_expires = timedelta(hours=1)

    access_token = create_access_token(
        data={"sub": str(user.user_id)},
        expires_delta=access_token_expires
    )

    # 5. 取得頭像資訊
    user_setting = db.query(Setting).filter(Setting.user_id == user.user_id).first()

    # --- 🌟 核心：精準寫入登入紀錄 ---
    try:
        # A. 裝置辨識
        ua_string = request.headers.get("user-agent", "")
        user_agent = parse(ua_string)

        # 針對 Win11 隱私標頭做微調 (若有)
        os_info = f"{user_agent.os.family} {user_agent.os.version_string}"
        if "Windows" in os_info and "10" in os_info:
            os_info = "Windows 11/10" # 標註相容版本

        device_name = f"{os_info}"
        if user_agent.is_mobile:
            device_name = f"{user_agent.device.model} ({user_agent.os.family})"

        browser_name = f"{user_agent.browser.family} {user_agent.browser.version_string}"

        # B. 精準縣市定位
        client_host = request.client.host if request.client else "127.0.0.1"
        location_name = "台灣"

        # 排除本機 IP，避免呼叫 API 浪費資源
        if client_host != "127.0.0.1" and client_host != "localhost":
            try:
                # 呼叫定位 API (繁體中文版)
                with httpx.Client() as client:
                    resp = client.get(f"http://ip-api.com/json/{client_host}?lang=zh-TW", timeout=2.0)
                    geo_data = resp.json()
                    if geo_data.get("status") == "success":
                        location_name = f"{geo_data.get('regionName', '')} {geo_data.get('city', '')}".strip()
            except Exception:
                location_name = "台灣 (定位暫不可用)"

        # C. 維護紀錄 (先將此 User 其他紀錄改為 False，再存入最新一筆)
        db.query(LoginActivity).filter(LoginActivity.user_id == user.user_id).update({"is_current": False})

        new_login_log = LoginActivity(
            user_id=user.user_id,
            ip_address=client_host,
            device_info=device_name,
            browser=browser_name,
            location=location_name,
            is_current=True
        )
        db.add(new_login_log)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"DEBUG: 寫入登入紀錄失敗: {e}")

    return {
        "msg": "登入成功",
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "name": user.name,
            "avatar_url": user_setting.avatar_url if user_setting else None,
        },
    }


# --- Google 登入相關 ---
class GoogleAuthRequest(BaseModel):
    token: str = Field(..., description="Google ID Token", examples=["GOOGLE_ID_TOKEN_EXAMPLE"])
    line_user_id: Optional[str] = None  # 🌟 讓後端可以接收前端傳來的 LINE ID


# key寫在.env
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")


@router.post("/auth/google", summary="📍Google 第三方登入/註冊")
async def google_auth(data: GoogleAuthRequest,
                    request: Request,
                    db: Session = Depends(get_db)):
    """
    接收前端 Google SDK 產生的 `id_token` 進行後端驗證。

    - **核心邏輯 (智慧流程)**:
        - **自動登入**: 若 Email 已存在，直接簽發 JWT Token 登入。
        - **自動註冊**: 若 Email 不存在，系統將自動完成以下動作：
            1. **建立帳號**: 隨機生成密碼與使用者名稱。
            2. **初始化帳產**: 自動建立「我的錢包」與「預設銀行」帳戶。
            3. **完成登入**: 直接回傳 JWT Token，不需額外註冊。

    - **資安機制**:
        - 使用 `google-auth` 官方庫進行 Token 簽章驗證。
        - 採用資料庫 Transaction (原子化)，確保會員與帳戶資料一致性。

    - **錯誤代碼**:
        - `400`: Google Token 驗證無效或過期。
    """

    # 1. 驗證 Google Token
    try:
        id_info = id_token.verify_oauth2_token(
            data.token, google_requests.Request(), GOOGLE_CLIENT_ID
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Google Token 驗證無效")

    # 2. 取得 Google 使用者資訊
    email = id_info["email"]
    full_name = id_info.get("name", "Google 使用者")

    # 3. 檢查使用者是否已存在
    user = db.query(Member).filter(Member.email == email).first()

    # 4. 如果使用者不存在，執行註冊流程
    if not user:
        default_username = f"{email.split('@')[0]}_{datetime.now().strftime('%M%S')}"
        new_user = Member(
            username=default_username,
            name=full_name,
            email=email,
            password=get_password_hash(str(uuid.uuid4())),
            role="user",
            status="active",
            created_at=datetime.now(),
            job="一般用戶",
        )
        db.add(new_user)
        db.flush()

        default_accounts = [
            Account(
                user_id=new_user.user_id,
                account_type="現金", account_name="我的錢包", currency="NT$",
                initial_balance=0, current_balance=0, account_icon="💰"
            ),
            Account(
                user_id=new_user.user_id,
                account_type="銀行", account_name="預設銀行", currency="NT$",
                initial_balance=0, current_balance=0, account_icon="🏦"
            ),
        ]
        db.add_all(default_accounts)
        db.commit()
        db.refresh(new_user)
        user = new_user

    # 🌟 核心：如果有傳入 line_user_id，就寫入資料庫完成綁定
    if data.line_user_id:
        user.line_user_id = data.line_user_id
        db.commit()

    # 5. 簽發 JWT Token
    access_token = create_access_token(data={"sub": str(user.user_id)})

    # --- 🌟 核心：寫入登入紀錄 (放在 return 前面，獨立 try-except) ---
    try:
        ua_string = request.headers.get("user-agent", "")
        user_agent = parse(ua_string)
        device_name = f"{user_agent.os.family} {user_agent.os.version_string}"
        browser_name = f"{user_agent.browser.family} {user_agent.browser.version_string}"

        if user_agent.is_mobile:
            device_name = f"{user_agent.device.model} ({user_agent.os.family})"

        client_host = request.client.host if request.client else "127.0.0.1"

        db.query(LoginActivity).filter(LoginActivity.user_id == user.user_id).update({"is_current": False})

        new_login_log = LoginActivity(
            user_id=user.user_id,
            ip_address=client_host,
            device_info=device_name,
            browser=browser_name,
            location="台灣",
            is_current=True
        )
        db.add(new_login_log)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Google 登入紀錄失敗: {e}")

    return {
        "msg": "Google 登入成功",
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email,
            "name": user.name,
        },
    }


@router.post("/auth/forgot-password/verify-otp", summary="✅ 驗證 OTP 代碼")
async def verify_otp(data: VerifyOTPRequest, db: Session = Depends(get_db)):
    """
    檢查使用者輸入的驗證碼是否有效。

    - **驗證條件**:
        - Email 與 OTP 必須匹配。
        - **時效性**: 必須在 5 分鐘內。
        - **一次性**: 該 OTP 必須標記為 `is_used=False` (未被使用過)。
    """

    # 🌟 修正 Ruff E712：使用 .is_(False) 替代 == False
    record = (
        db.query(PasswordReset)
        .filter(
            PasswordReset.email == data.email,
            PasswordReset.otp_code == data.otp,
            PasswordReset.is_used.is_(False),
            PasswordReset.expires_at > datetime.now(),
        )
        .order_by(PasswordReset.created_at.desc())
        .first()
    )

    if not record:
        raise HTTPException(status_code=400, detail="驗證碼錯誤或已過期")

    return {"msg": "驗證通過，請重新設定新密碼"}


@router.post("/auth/forgot-password/reset", summary="🔑 重設新密碼")
async def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    """
    設定新的登入密碼。

    - **前置條件**: 必須先通過 OTP 驗證。
    - **行為**:
        1. 更新密碼 (Hash 加密)。
        2. 將該次 OTP 標記為 `is_used=True`，使其失效。
    """

    # 🌟 修正 Ruff E712：使用 .is_(False) 替代 == False
    record = (
        db.query(PasswordReset)
        .filter(
            PasswordReset.email == data.email,
            PasswordReset.otp_code == data.otp,
            PasswordReset.is_used.is_(False),
        )
        .first()
    )

    if not record:
        raise HTTPException(status_code=400, detail="請求無效，請重新進行驗證流程")

    user = db.query(Member).filter(Member.email == data.email).first()
    if user is None:
        raise HTTPException(status_code=404, detail="找不到該使用者，無法重設密碼")

    user.password = get_password_hash(data.new_password)
    record.is_used = True

    db.commit()
    return {"msg": "密碼已成功修改！"}


@router.post("/auth/token", summary="🔓 Swagger UI 專用登入", include_in_schema=False)
async def login_for_swagger(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    """
    (此 API 僅供 Swagger 右上角 'Authorize' 按鈕使用，前端請勿串接此接口)
    """

    user = (
        db.query(Member)
        .filter(
            (Member.username == form_data.username)
            | (Member.email == form_data.username)
        )
        .first()
    )

    if not user:
        raise HTTPException(status_code=401, detail="帳號不存在或輸入錯誤")

    if not verify_password(form_data.password, user.password):
        raise HTTPException(status_code=401, detail="密碼錯誤")

    access_token = create_access_token(data={"sub": str(user.user_id)})

    return {"access_token": access_token, "token_type": "bearer"}

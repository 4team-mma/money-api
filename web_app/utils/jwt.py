"""
JWT 工具函式
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from dotenv import load_dotenv
from fastapi import HTTPException, status
from jose import JWTError, jwt, ExpiredSignatureError


load_dotenv()

# 取得與 main.py 一致的 logger
logger = logging.getLogger(__name__)

# JWT 設定
# 1. 移除預設值，強迫必須從環境變數讀取
SECRET_KEY = os.getenv("SECRET_KEY")

# 2. 嚴格的安全檢查：不允許為空，也不允許使用開發期常見的弱密鑰
if not SECRET_KEY or SECRET_KEY == "your-secret-key-keep-it-secret":
    logger.critical("FATAL ERROR: 系統缺少安全的 SECRET_KEY 環境變數！")
    raise ValueError("正式環境必須設定安全且隨機的 SECRET_KEY，伺服器啟動失敗。")

ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    建立 Access Token

    Args:
        data: 要編碼到 Token 中的資料
        expires_delta: 過期時間（可選）

    Returns:
        JWT Token 字串
    """
    to_encode = data.copy()

    # 設定過期時間
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})  # 🌟 標記類型
    # 編碼 JWT
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """
    建立 Refresh Token

    Args:
        data: 要編碼到 Token 中的資料

    Returns:
        JWT Refresh Token 字串
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})  # 標記為 refresh token
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> dict:
    """
    驗證 Token 並解碼
    🌟 優化：區分過期與非法憑證，且不觸發全域 500 Log
    """
    try:
        # 解碼 JWT
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # 1. 檢查必要欄位
        if not payload.get("sub"):
            logger.warning("Token 解析成功但缺少 'sub' 欄位")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="憑證格式錯誤",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload

    except ExpiredSignatureError:
        # 🌟 明確拋出「過期」訊息，讓前端 Vue 攔截器決定是否執行 Refresh Token 流程
        logger.info("使用者憑證已過期")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登入時間過長，已自動退出",  # 使用特定字串方便前端判斷
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as e:
        # 🌟 其他 JWT 錯誤（簽名不符、格式不對等）
        # 這裡 raise HTTPException 不會進入 main.py 的 500 全域處理器
        logger.warning(f"Token 驗證無效: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="無法驗證憑證",
            headers={"WWW-Authenticate": "Bearer"},
        )


def decode_token(token: str) -> Optional[dict]:
    """解碼 Token（不驗證，僅用於後端內部快速讀取）"""
    try:
        return jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"verify_signature": False},
        )
    except JWTError:
        return None

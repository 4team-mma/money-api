"""
JWT 工具函式
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import HTTPException, status
from jose import JWTError, jwt

load_dotenv()

# JWT 設定
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-keep-it-secret")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
)
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


def create_access_token(
    data: dict, expires_delta: Optional[timedelta] = None
) -> str:
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
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update({"exp": expire})

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
    expire = datetime.now(timezone.utc) + timedelta(
        days=REFRESH_TOKEN_EXPIRE_DAYS
    )
    to_encode.update({"exp": expire, "type": "refresh"})  # 標記為 refresh token

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> dict:
    """
    驗證 Token 並解碼

    Args:
        token: JWT Token 字串

    Returns:
        解碼後的 Payload

    Raises:
        HTTPException: Token 無效或過期
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="無法驗證憑證",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # 解碼 JWT
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # 檢查必要欄位
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception

        return payload

    except JWTError:
        raise credentials_exception


def decode_token(token: str) -> Optional[dict]:
    """
    解碼 Token（不驗證）

    Args:
        token: JWT Token 字串

    Returns:
        解碼後的 Payload，失敗返回 None
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

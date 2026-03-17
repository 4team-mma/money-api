# web_app/dependencies.py
# 我是守門員!從http header抓取token,然後用jwt驗證是否偽造過期,
# 再去資料庫抓user物件,把user物件交給路由。

from fastapi import Depends, HTTPException, status,Query, WebSocketException
from sqlalchemy.orm import Session
from .database import get_db
from .models import Member
from .utils.jwt import verify_token
from fastapi.security import OAuth2PasswordBearer

# 這是 FastAPI 用來告訴 Swagger UI "Token 網址在哪" 的設定
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


# 1. 取得當前使用者物件 (而不只是 ID)
def get_current_user(
    db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)
) -> Member:
    payload = verify_token(token)
    user_id = payload.get("sub")
    user = db.query(Member).filter(Member.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="無效的驗證憑證")
    return user


# 2. 強制檢查是否為管理員
def admin_required(current_user: Member = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="權限不足，僅限管理員存取"
        )
    return current_user


# 🌟 新增：專門給 WebSocket 用的驗證守門員
async def get_current_user_ws(
    token: str = Query(..., description="WebSocket Token"),
    db: Session = Depends(get_db)
) -> Member:
    try:
        # 沿用你原本的 verify_token
        payload = verify_token(token) 
        user_id = payload.get("sub")
        user = db.query(Member).filter(Member.user_id == user_id).first()
        if not user:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
        return user
    except Exception:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
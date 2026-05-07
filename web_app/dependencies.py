# web_app/dependencies.py
# 我是守門員!從http header抓取token,然後用jwt驗證是否偽造過期,
# 再去資料庫抓user物件,把user物件交給路由。

from fastapi import Depends, HTTPException, status, Request, WebSocketException,WebSocket
from sqlalchemy.orm import Session
from .database import get_db
from .models import Member
from .utils.jwt import verify_token
from fastapi.security import OAuth2PasswordBearer

# 這是 FastAPI 用來告訴 Swagger UI "Token 網址在哪" 的設定
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


# 1. 取得當前使用者物件 (而不只是 ID)
def get_current_user(
    request: Request, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)
) -> Member:
    try:
        payload = verify_token(token)
        user_id = payload.get("sub")
        user = db.query(Member).filter(Member.user_id == user_id).first()

        if not user:
            raise HTTPException(status_code=401, detail="無效的驗證憑證")

        # 備份純字串 (供 Exception Handler 穩定抓取)
        # 即使 user 物件後來在 DB Error 中失效，這兩個字串也會永遠留在 request 裡
        request.state.user_id_str = str(user.user_id)
        request.state.username_str = str(user.username)

        return user
    except Exception:
        raise HTTPException(status_code=401, detail="憑證解析失敗")


# 2. 強制檢查是否為管理員
def admin_required(current_user: Member = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="權限不足，僅限管理員存取"
        )
    return current_user


# 專門給 WebSocket 用的驗證守門員
async def get_current_user_ws(
    websocket: WebSocket, # 改成接收 websocket 物件
    db: Session = Depends(get_db)
) -> Member:
    try:
        # 從 Header 中提取前端傳過來的 Subprotocol (也就是我們的 token)
        protocols = websocket.headers.get("sec-websocket-protocol")
        if not protocols:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
        
        # 瀏覽器傳過來可能會包含多個值，取第一個並去除空白
        token = protocols.split(",")[0].strip()

        # 沿用你原本的 verify_token
        payload = verify_token(token)
        user_id = payload.get("sub")
        user = db.query(Member).filter(Member.user_id == user_id).first()
        
        if not user:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
            
        # 🌟 重要：把 token 存進 state，下一步路由會用到
        websocket.state.ws_token = token
        
        return user
    except Exception:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
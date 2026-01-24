# web_app/dependencies.py 

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from .database import get_db
from .models import Member
from .utils.jwt import verify_token
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

# 1. 取得當前使用者物件 (而不只是 ID)
def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> Member:
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
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="權限不足，僅限管理員存取"
        )
    return current_user
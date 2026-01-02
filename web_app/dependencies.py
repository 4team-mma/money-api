# web_app/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from .utils.jwt import verify_token

# tokenUrl 指向你實作登入 API 的路徑，例如 auth.py 裡的 login 路徑
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login") 

def get_current_user_id(token: str = Depends(oauth2_scheme)) -> int:
    """
    全域守門員：從 Token 裡解析出當前使用者的 user_id
    """
    payload = verify_token(token)
    user_id = payload.get("sub")
    
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="無效的驗證憑證",
        )
    return int(user_id)
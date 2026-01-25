import bcrypt

# ==================== 輔助函式 ====================

# 註冊時使用,將密碼轉成encode
def get_password_hash(password: str) -> str:
    """雜湊密碼"""
    
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")
    

# 登入時使用
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """驗證密碼"""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), 
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False
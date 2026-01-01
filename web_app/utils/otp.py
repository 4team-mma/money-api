import random
import string

def generate_otp(length: int = 6) -> str:
    """產生指定長度的純數字驗證碼"""
    # 使用 random.choices 確保產生的是字串，並處理開頭為 0 的情況
    return ''.join(random.choices(string.digits, k=length))
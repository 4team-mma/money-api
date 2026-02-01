# import random
import string
import secrets


def generate_otp(length: int = 6) -> str:
    """產生加密級別安全的純數字驗證碼"""
    # secrets.choice 比 random.choice 更難被預測
    return "".join(secrets.choice(string.digits) for _ in range(length))

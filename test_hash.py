# test_hash.py
# 請確保你在終端機執行: uv run python test_hash.py
from passlib.context import CryptContext

# 初始化加密工具，這裡的設定必須跟後端 utils/password.py 一致
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

p1 = "123"
p2 = "12345"

print("-" * 30)
print(f"123 的雜湊碼 (給 user 帳號):")
print(pwd_context.hash(p1))
print("-" * 30)
print(f"12345 的雜湊碼 (給 admin 帳號):")
print(pwd_context.hash(p2))
print("-" * 30)
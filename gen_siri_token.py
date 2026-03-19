import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from jose import jwt # 確保妳有安裝 python-jose
# python gen_siri_token.py
# 1. 載入 .env 變數
load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-keep-it-secret")
ALGORITHM = os.getenv("ALGORITHM", "HS256")

# 2. 產出 ID 為 6 的長效 Token (有效期 1 年)
user_id = "6"
expire_delta = timedelta(days=365)
expire_time = datetime.now(timezone.utc) + expire_delta

to_encode = {
    "sub": str(user_id),
    "exp": expire_time,
    "type": "access"
}

encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

print("\n" + "="*50)
print(f"DEBUG: SECRET_KEY 前五碼: {SECRET_KEY[:5]}...")
print(f"DEBUG: 使用者 ID: {user_id}")
print(f"DEBUG: 過期時間: {expire_time}")
print("-" * 50)
print(f"Bearer {encoded_jwt}")
print("="*50 + "\n")
print("請複製上面整串(含 Bearer 與空格)到 Siri 捷徑喵！")
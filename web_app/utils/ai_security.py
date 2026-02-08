from cryptography.fernet import Fernet
import os
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

# 從 .env 讀取密鑰，如果沒有則產生一個 (建議在 .env 設定 ENCRYPTION_KEY)
# 你可以用 Fernet.generate_key().decode() 產生一組填入 .env
ENCRYPT_KEY = os.getenv("ENCRYPTION_KEY")

if not ENCRYPT_KEY:
    # 警告：如果沒設 key，每次重啟 server 會導致舊資料解不開
    # 開發測試時暫時產生，正式環境務必固定
    ENCRYPT_KEY = Fernet.generate_key()
else:
    ENCRYPT_KEY = ENCRYPT_KEY.encode()

cipher_suite = Fernet(ENCRYPT_KEY)

def encrypt_api_key(plain_key: Optional[str]) -> Optional[str]:
    """加密 API Key"""
    if not plain_key:
        return None # 現在這裡不會跳紅線了
    return cipher_suite.encrypt(plain_key.encode()).decode()

# 解密函數
def decrypt_api_key(encrypted_key: Optional[str]) -> Optional[str]:
    """解密 API Key"""
    if not encrypted_key:
        return None
    try:
        return cipher_suite.decrypt(encrypted_key.encode()).decode()
    except Exception:
        return "DECRYPT_ERROR"
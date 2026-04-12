# email_utils.py 只管「怎麼驗、怎麼寄」
import logging
import smtplib
import os
import socket
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import requests



# --- 🚀 修正 Render IPv6 連線阻擋的 Bug (加上這段) ---
old_getaddrinfo = socket.getaddrinfo
def ipv4_getaddrinfo(*args, **kwargs):
    responses = old_getaddrinfo(*args, **kwargs)
    return [response for response in responses if response[0] == socket.AF_INET]
socket.getaddrinfo = ipv4_getaddrinfo
# --------------------------------------------------

load_dotenv()

RECAPTCHA_SECRET = os.getenv("RECAPTCHA_SECRET_KEY")


def verify_recaptcha(token: str) -> bool:
    """
    使用 REST API 方式驗證 Google reCAPTCHA
    """
    verify_url = "https://www.google.com/recaptcha/api/siteverify"
    payload = {"secret": RECAPTCHA_SECRET, "response": token}
    # 發送 REST 請求到 Google
    response = requests.post(verify_url, data=payload, timeout=5)
    response.raise_for_status()
    result = response.json()

    # Google 會回傳 success (布林值) 與 score (0.0 ~ 1.0)
    # score 越高代表越像人類，通常設定 > 0.5 即可通過
    # Google 回傳的 success 代表 API 呼叫是否成功，score 才是分數
    return result.get("success", False) and result.get("score", 0) > 0.5


# 從 .env 讀取設定
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")  # 你的 Gmail 帳號
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")  # 你的 Gmail 應用程式密碼

logger = logging.getLogger(__name__)


def send_otp_email(receiver_email: str, otp_code: str):
    """實作寄送驗證碼郵件"""

    # 1. 環境變數檢查 (改用 logger)
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.error("SMTP 設定缺失：未設定 SMTP_USER 或 SMTP_PASSWORD")
        return False

    # 2. 建立郵件內容
    message = MIMEMultipart()
    message["From"] = f"Money MMA 管理團隊 <{SMTP_USER}>"
    message["To"] = receiver_email
    message["Subject"] = "【Money MMA】您的密碼重置驗證碼"

    body = f"""
    <html>
        <body style="font-family: sans-serif;">
            <h2>您好：</h2>
            <p>我們收到了您重設密碼的請求。請在網頁上輸入以下驗證碼以繼續：</p>
            <h1 style="color: #3B82F6; font-size: 32px; letter-spacing: 5px;">{otp_code}</h1>
            <p>此驗證碼將於 5 分鐘後過期。我們不會打電話向您索取任何資訊。若您未申請，請忽略。</p>
            <hr style="border: 0; border-top: 1px solid #eee;" />
            <p style="color: #888; font-size: 12px;">Money MMA 團隊 敬上</p>
        </body>
    </html>
    """
    message.attach(MIMEText(body, "html"))

    # 3. 連接伺服器並發信
    try:
        # 強制 IPv4 補丁 (保留這段)
        addr_info = socket.getaddrinfo(SMTP_SERVER, SMTP_PORT, socket.AF_INET, socket.SOCK_STREAM)
        target_ip = str(addr_info[0][4][0])
        
        # 🌟 自動判斷 Port：如果是 465 就用 SMTP_SSL，否則用一般 SMTP
        if SMTP_PORT == 465:
            logger.info("🚀 使用 Port 465 (SSL) 寄信模式")
            server = smtplib.SMTP_SSL(target_ip, SMTP_PORT, timeout=10)
        else:
            logger.info("🚀 使用 Port 587 (TLS) 寄信模式")
            server = smtplib.SMTP(target_ip, SMTP_PORT, timeout=10)
            server.starttls()

        with server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(message)
            
        logger.info(f"✅ 驗證碼已成功寄送至: {receiver_email}")
        return True

    except Exception as e:
        logger.error(f"❌ 寄信失敗，詳細原因: {str(e)}")
        return False
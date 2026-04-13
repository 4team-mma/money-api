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
    """
    具備自動切換功能的寄信函式：
    - 雲端偵測到 SENDGRID_API_KEY 時：走 HTTP API (繞過連接埠封鎖)
    - 地端或未設定 Key 時：走原本穩定的 SMTP 邏輯
    """
    sendgrid_key = os.getenv("SENDGRID_API_KEY")
    
    # --- 1. 建立共同的郵件 HTML 內容 (確保地端雲端長相一致) ---
    email_body = f"""
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

    # --- 🚀 A模式：雲端 SendGrid API 模式 (HTTPS Port 443) ---
    if sendgrid_key:
        print(f"\n🚀 [SENDGRID API] 偵測到 Key，準備寄信至: {receiver_email}")
        url = "https://api.sendgrid.com/v3/mail/send"
        headers = {
            "Authorization": f"Bearer {sendgrid_key}",
            "Content-Type": "application/json"
        }
        data = {
            "personalizations": [{"to": [{"email": receiver_email}]}],
            "from": {"email": SMTP_USER, "name": "Money MMA 管理團隊"},
            "subject": "【Money MMA】您的密碼重置驗證碼",
            "content": [{"type": "text/html", "value": email_body}]
        }
        try:
            response = requests.post(url, json=data, headers=headers, timeout=10)
            if response.status_code in [200, 201, 202]:
                print(f"✅ [SENDGRID SUCCESS] 郵件已透過 API 成功送出！")
                logger.info(f"✅ SendGrid API 寄送成功: {receiver_email}")
                return True
            else:
                print(f"❌ [SENDGRID ERROR] 狀態碼: {response.status_code}, 原因: {response.text}")
                return False
        except Exception as e:
            print(f"❌ [SENDGRID CRASH] API 連線失敗: {str(e)}")
            return False

    # --- 🏠 B模式：原本的 SMTP 模式 (用於地端開發) ---
    else:
        print(f"\n🏠 [SMTP DEBUG] 未偵測到 API Key，切換至傳統 SMTP 模式...")
        
        if not SMTP_USER or not SMTP_PASSWORD:
            logger.error("SMTP 設定缺失：未設定 SMTP_USER 或 SMTP_PASSWORD")
            return False

        message = MIMEMultipart()
        message["From"] = f"Money MMA 管理團隊 <{SMTP_USER}>"
        message["To"] = receiver_email
        message["Subject"] = "【Money MMA】您的密碼重置驗證碼"
        message.attach(MIMEText(email_body, "html"))

        try:
            print(f"📬 [SMTP DEBUG] 開始連線程序，目標: {receiver_email}")
            print(f"DEBUG: 正在確認 {SMTP_SERVER} 的 DNS 解析...")
            addr_info = socket.getaddrinfo(SMTP_SERVER, SMTP_PORT, socket.AF_INET, socket.SOCK_STREAM)
            print(f"DEBUG: 解析成功，目標 IPv4 為: {addr_info[0][4][0]}")
            
            if SMTP_PORT == 465:
                print(f"🚀 DEBUG: 嘗試使用 Port 465 (SSL) 連線至 {SMTP_SERVER}")
                server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=15)
            else:
                print(f"🚀 DEBUG: 嘗試使用 Port 587 (TLS) 連線至 {SMTP_SERVER}")
                server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15)
                server.starttls()

            with server:
                print("DEBUG: 正在執行 SMTP Login...")
                server.login(SMTP_USER, SMTP_PASSWORD)
                print("DEBUG: Login 成功，發送郵件中...")
                server.send_message(message)
                
            print(f"✅ [SMTP SUCCESS] 驗證碼已寄送至: {receiver_email}")
            logger.info(f"✅ SMTP 寄送成功: {receiver_email}")
            return True

        except Exception as e:
            print(f"❌ [SMTP ERROR] 寄信崩潰！原因: {str(e)}")
            logger.error(f"❌ 寄信失敗，詳細原因: {str(e)}")
            return False
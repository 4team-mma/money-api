import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

# 從 .env 讀取設定
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")      # 你的 Gmail 帳號
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")  # 你的 Gmail 應用程式密碼

def send_otp_email(receiver_email: str, otp_code: str):
    """實作寄送驗證碼郵件"""
    if not SMTP_USER or not SMTP_PASSWORD:
        print("❌ 錯誤：未設定 SMTP 帳號或密碼，無法發信")
        return False

    # 建立郵件內容
    message = MIMEMultipart()
    message["From"] = f"Money MMA 管理團隊 <{SMTP_USER}>"
    message["To"] = receiver_email
    message["Subject"] = "【Money MMA】您的密碼重置驗證碼"

    body = f"""
    <html>
        <body>
            <h2>您好：</h2>
            <p>我們收到了您重設密碼的請求。請在網頁上輸入以下驗證碼以繼續：</p>
            <h1 style="color: #3B82F6; font-size: 32px;">{otp_code}</h1>
            <p>此驗證碼將於 5 分鐘後過期。如果您並未要求重設密碼，請忽略此郵件。</p>
            <br>
            <p>Money MMA 團隊 敬上</p>
        </body>
    </html>
    """
    message.attach(MIMEText(body, "html"))

    try:
        # 連接伺服器並發信
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()  # 啟用安全傳輸
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(message)
        return True
    except Exception as e:
        print(f"❌ 寄信失敗：{e}")
        return False
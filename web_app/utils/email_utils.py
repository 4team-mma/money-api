import logging
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
            <p>此驗證碼將於 5 分鐘後過期。如果您並未要求重設密碼，請忽略此郵件。</p>
            <hr style="border: 0; border-top: 1px solid #eee;" />
            <p style="color: #888; font-size: 12px;">Money MMA 團隊 敬上</p>
        </body>
    </html>
    """
    message.attach(MIMEText(body, "html"))

    try:
        # 3. 連接伺服器並發信
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            server.starttls()  # 啟用安全傳輸
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(message)
        logger.info(f"✅ 驗證碼已成功寄送至: {receiver_email}")
        return True

    except (smtplib.SMTPException, OSError) as e:
        # 4. 這裡紀錄 Log，但將布林值傳回給 API，由 API 決定是否 raise HTTPException
        logger.error(f"❌ 寄信失敗 (對象: {receiver_email}): {str(e)}", exc_info=True)
        return False
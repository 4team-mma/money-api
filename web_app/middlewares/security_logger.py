# web_app/middlewares/security_logger.py
import logging
import json
import os
from datetime import datetime

# 1. 設定專屬的 Security Logger
os.makedirs("logs", exist_ok=True)
sec_logger = logging.getLogger("security_audit")
sec_logger.setLevel(logging.INFO)

if not sec_logger.handlers:
    file_handler = logging.FileHandler("logs/security_audit.log", encoding="utf-8")
    sec_logger.addHandler(file_handler)

# 🚀 終極解法：純 ASGI Middleware 寫法
class SecurityAuditMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # 🚨 最關鍵的防護：只要不是 HTTP (例如 WebSocket)，直接放行，完全不干涉底層通道！
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 以下是專門攔截 HTTP 請求的邏輯
        response_status = [500]

        # 偷偷紀錄 FastAPI 回傳的狀態碼
        async def custom_send(message):
            if message["type"] == "http.response.start":
                response_status[0] = message["status"]
            await send(message)

        # 讓請求繼續往下走
        try:
            await self.app(scope, receive, custom_send)
        finally:
            status_code = response_status[0]
            # 🚨 核心邏輯：只記錄潛在攻擊
            if status_code in [401, 403, 404, 429]:
                # 抓取 IP 等資訊
                client = scope.get("client")
                ip = client[0] if client else "unknown"
                method = scope.get("method", "unknown")
                path = scope.get("path", "unknown")
                
                # 抓取 user_agent
                headers = dict(scope.get("headers", []))
                user_agent = headers.get(b"user-agent", b"unknown").decode("utf-8")

                log_data = {
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "ip": ip,
                    "method": method,
                    "path": path,
                    "status": status_code,
                    "user_agent": user_agent
                }
                sec_logger.info(json.dumps(log_data))
import os
from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
import logging as logger
router = APIRouter()

@router.get("/") 
async def root(request: Request):
    """
    API 系統狀態檢查
    """
    # 取得真實 IP (若有經過 Nginx/Cloudflare 需改用 X-Forwarded-For，這裡先用簡易版)
    client_host = request.client.host if request.client else "unknown"
    logger.info(f"訪客 {client_host} 訪問了系統首頁")

    return {
        "app_name": "FastAPI MoneyMMA",  # 專案名稱
        "version": "1.0.0",              # 版本號 (跟 Swagger 上的一致)
        "status": "online",              # 系統狀態
        "server_time": datetime.now().isoformat(), # 伺服器時間 (方便除錯時區問題)
        "support": "如有疑問，請至網站問題回饋留言" # 聯絡方式 (選填)
    }
    

from fastapi import APIRouter
from fastapi import APIRouter, Request
import logging  # 1. 匯入日誌模組
import os
# 2. 取得這份檔案專用的紀錄器
logger = logging.getLogger("root")

router = APIRouter()

@router.get("/")
async def root(request: Request):
    client_host = request.client.host  # 取得訪問者 IP
    logger.info(f'來自{client_host}訪客,訪問了首頁')  # 3. 紀錄動作
    return {"hello": "Hello! Welcome to MMA web",
            "key": os.getenv('SECRET_KEY','沒有設定'),
            "path":os.getenv('PATH','沒有設定') 
            # 作業系統本身的環境變數
            }

@router.get("/loot")
async def get_loot():
    # logger.info("訪問了 loot 頁面")
    return {"item":"我是loot"}
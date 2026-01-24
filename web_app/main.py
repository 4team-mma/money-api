from dotenv import load_dotenv
import os
from fastapi import FastAPI,Request,Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from web_app.routes import root, users, accounts, records, auth,admin,transfers,feedback,analysis

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager
from .utils.cpi_crawler import fetch_and_update_cpi
from web_app.dependencies import admin_required


# 1. 先載入環境變數
load_dotenv()

# Jinja當測試?
templates = Jinja2Templates(directory="web_app/templates")

# 2. 建立資料夾 (必須在日誌設定之前)
log_file_path = os.getenv("LOG_FILE", "logs/app.log")
log_dir = os.path.dirname(log_file_path)
if log_dir:
    os.makedirs(log_dir, exist_ok=True)

# 3. 設定基礎日誌格式 (全域設定一次就好)
logging.basicConfig(
    filename=log_file_path,
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    encoding="utf-8"
)
# --------------------------------------
# 🔥 新增：定義生命週期管理器 (Lifespan)
# 這裡負責在伺服器啟動時開啟排程，關閉時停止排程
@asynccontextmanager
async def lifespan(_: FastAPI):
    # --- 啟動時執行 ---
    scheduler = BackgroundScheduler()
    
    # 設定排程：這裡設定每天凌晨 04:00 執行一次更新
    # 也可以改成 hours=1 (每小時) 或 minutes=30 (每30分)
    scheduler.add_job(fetch_and_update_cpi, 'cron', hour=4, minute=0)
    
    scheduler.start()
    logging.info("APScheduler 排程器已啟動 - 每日 04:00 更新 CPI 資料")
    
    yield # 分隔線，以上是啟動，以下是關閉
    
    # --- 關閉時執行 ---
    scheduler.shutdown()
    logging.info("APScheduler 排程器已關閉")
# --------------------------------------
# 配置
DEBUG = os.getenv("DEBUG", "true").lower() == "true"

app = FastAPI(
    title="FastAPI MoneyMMA",
    description="MMA server API-project",
    version="1.0.0",
    lifespan=lifespan,  # <--- 加上這一行，排程才會動！
    docs_url="/docs" if DEBUG else None,
    redoc_url="/redoc" if DEBUG else None,
    openapi_url="/openapi.json" if DEBUG else None,
)

# 1. 讀取 .env 的字串的5173,5174
cors_raw = os.getenv("CORS_ORIGINS", "")
origins = [origin.strip() for origin in cors_raw.split(",") if origin.strip()]

# --- 中間件設定 (Middleware) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 路由註冊 (Routers) ---
# 基礎路由
app.include_router(root.router)

# 
# 分支_使用 prefix 
app.include_router(auth.router, prefix="/api", tags=["認證與密碼管理"])
app.include_router(users.router, prefix="/api/users", tags=["使用者"])
app.include_router(accounts.router, prefix="/api/accounts", tags=["帳戶"])
app.include_router(records.router, prefix="/api/records", tags=["收支紀錄"])
app.include_router(transfers.router, prefix="/api/transfers", tags=["轉帳紀錄"])
app.include_router(feedback.router, prefix="/api/feedback", tags=["問題回饋"])
app.include_router(
    admin.router, 
    prefix="/api/admin", 
    tags=["系統管理後台"],
    dependencies=[Depends(admin_required)] #  admin/ 底下的所有網址都限管理員
)
app.include_router(analysis.router,prefix="/api/analysis",tags=["消費趨勢分析"])

@app.get("/favicon.ico")
async def favicon():
    return RedirectResponse("/static/favicon.ico")

@app.get("/jinja")
def jinja(request:Request):
    return templates.TemplateResponse(request=request,name="test.jinja",context={"第一組":"money"})

app.mount("/static",StaticFiles(directory="web_app/static"), name="static")
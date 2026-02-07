from dotenv import load_dotenv
import os
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from web_app.routes import (
    root,
    users,
    accounts,
    records,
    auth,
    admin,
    transfers,
    feedback,
    analysis,
    reminders,
)
from web_app.routes.setting import router as setting_router
from web_app.routes.stats import router as stats_router
from web_app.dependencies import admin_required
from web_app.utils.cpi_crawler import fetch_and_update_cpi
from web_app.utils.salary_crawler import run_all_salary_tasks
from fastapi.responses import RedirectResponse, JSONResponse
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from contextlib import asynccontextmanager
from sqlalchemy.exc import SQLAlchemyError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import logging
from datetime import datetime,timedelta


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
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    encoding="utf-8",
)

# --------------------------------------
# 定義生命週期管理器 (Lifespan)
# 這裡負責在伺服器啟動時開啟排程，關閉時停止排程
@asynccontextmanager
async def lifespan(_: FastAPI):
    # --- 啟動時執行 ---
    scheduler = BackgroundScheduler()

    # ==========================
    # 任務 1: CPI 爬蟲
    # ==========================
    # A. 開機檢查 (10秒後)
    scheduler.add_job(
        fetch_and_update_cpi,
        "date",
        run_date=datetime.now() + timedelta(seconds=10),
        id="cpi_startup_check",
        replace_existing=True
    )
    # B. 定期排程 (每月 6 號)
    scheduler.add_job(
        fetch_and_update_cpi, "cron", day=6, hour=10, minute=0,
        id="cpi_monthly_update", replace_existing=True
    )

    # ==========================
    # 任務 2: 薪資爬蟲 (新增的部分)
    # ==========================
    # A. 開機檢查 (20秒後 - 錯開時間避免同時搶資源)
    scheduler.add_job(
        run_all_salary_tasks,
        "date",
        run_date=datetime.now() + timedelta(seconds=20),
        id="salary_startup_check",
        replace_existing=True
    )
    
    # B. 定期排程 (每月 20 號 - 薪資資料通常比較慢出來)
    scheduler.add_job(
        run_all_salary_tasks, "cron", day=20, hour=10, minute=0,
        id="salary_monthly_update", replace_existing=True
    )

    scheduler.start()
    logging.info("🚀 APScheduler 已啟動 - CPI(6號) & 薪資(20號) 自動更新中")

    yield  # 伺服器運作中...

    # --- 關閉時執行 ---
    scheduler.shutdown()
    logging.info("🛑 APScheduler 排程器已關閉")


# --------------------------------------
# 配置
DEBUG = os.getenv("DEBUG", "true").lower() == "true"


#  初始化 Limiter (slowapi：相關設定01)
# key_func 指定用 IP 位址作為限制對象
limiter = Limiter(key_func=get_remote_address)


# 貓貓
cat_logo = r"""
```text
    /\_____/\
   /  o   o  \  喵
  ( ==  ^  == )  喵
   )         (    1
  (           )	  號
 ( (  )   (  ) )
(__(__)___(__)__)
                                Welcome to MoneyMMA API!
                                            Meow~ 
    
"""


app = FastAPI(
    title="FastAPI MoneyMMA",
    description=f"這是 MoneyMMA 的後端 API 文件。 \n \n{cat_logo}",
    version="1.0.0",
    lifespan=lifespan,  # <--- 加上這一行，排程才會動！
    docs_url="/docs" if DEBUG else None,
    redoc_url="/redoc" if DEBUG else None,
    openapi_url="/openapi.json" if DEBUG else None,
)

# ----------------------------------------------------------------
# 🔥slowapi：相關設定02
# ----------------------------------------------------------------

# 將 limiter 掛載到 app 狀態，並註冊報錯處理器
app.state.limiter = limiter
# 異常處理區塊: 當使用者點擊太快時，自動回傳 429 Too Many Requests。


# 修改原因:Pylance跳出紅線警告
# 這個報錯是因為 FastAPI 的 add_exception_handler 預設預期處理函數的第二個參數要是通用的 Exception，但 slowapi 的內建處理器限定了必須是 RateLimitExceeded。
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return _rate_limit_exceeded_handler(request, exc)


# ----------------------------------------------------------------
# 🔥 新增：全域異常處理器 (Global Exception Handlers)
# ----------------------------------------------------------------

# 建立一個專門給 main 使用的 logger
logger = logging.getLogger(__name__)


# 處理所有未預期的崩潰 (Exception)
@app.exception_handler(Exception)
async def universal_exception_handler(request: Request, exc: Exception):
    # 紀錄詳細錯誤到 logs/app.log
    # exc_info=True 會自動抓取 Traceback (哪一行的程式碼出錯)
    logger.error(
        f"非預期錯誤 - 路徑: {request.url.path} - 錯誤內容: {str(exc)}", exc_info=True
    )

    # 回傳給前端安全、格式統一的訊息
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "detail": "系統發生非預期錯誤，請聯繫管理員或稍後再試。",
        },
    )


# 針對資料庫錯誤做更細緻的 Log
@app.exception_handler(SQLAlchemyError)
async def database_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.error(
        f"資料庫異常 - 路徑: {request.url.path} - 錯誤內容: {str(exc)}", exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={"success": False, "detail": "資料庫連線或處理異常，請稍後再試。"},
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
app.include_router(root.router, tags=["根目錄顯示"])

#
# 分支_使用 prefix
app.include_router(auth.router, prefix="/api", tags=["認證與密碼管理"])
app.include_router(users.router, prefix="/api/users", tags=["使用者"])
app.include_router(accounts.router, prefix="/api/accounts", tags=["帳戶"])
app.include_router(records.router, prefix="/api/records", tags=["收支紀錄"])
app.include_router(transfers.router, prefix="/api/transfers", tags=["轉帳紀錄"])
app.include_router(feedback.router, prefix="/api/feedback", tags=["問題回饋"])
app.include_router(reminders.router, prefix="/api/reminders", tags=["提醒事項"])
app.include_router(setting_router, prefix="/api/setting", tags=["設定項目"])
app.include_router(
    admin.router,
    prefix="/api/admin",
    tags=["系統管理後台"],
    dependencies=[Depends(admin_required)],  #  admin/ 底下的所有網址都限管理員
)
app.include_router(analysis.router, prefix="/api/analysis", tags=["消費趨勢分析"])
app.include_router(stats_router, prefix="/api/stats", tags=["圖表分析"])


@app.get("/favicon.ico", tags=["api圖標"])
async def favicon():
    return RedirectResponse("/static/favicon.ico")


@app.get("/jinja", tags=["jinja 後端頁面呈現檢測用"])
def jinja(request: Request):
    return templates.TemplateResponse(
        request=request, name="test.jinja", context={"第一組": "money"}
    )


app.mount("/static", StaticFiles(directory="web_app/static"), name="static")

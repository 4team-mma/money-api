from dotenv import load_dotenv
import os
import httpx
import re
import traceback
from fastapi import FastAPI, Request, Depends, BackgroundTasks
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
    ai_models,
    gamification,
    ai,
    ws,
    integrations
)
from web_app.routes.setting import router as setting_router
from web_app.routes.planning import router as planning_router
from web_app.routes.stats import router as stats_router

from web_app.dependencies import admin_required
from web_app.utils.cpi_crawler import fetch_and_update_cpi
from web_app.utils.salary_crawler import run_all_salary_tasks
from web_app.utils.notification_scheduler import cleanup_old_notifications
from web_app.utils.login_cleanup import cleanup_old_login_activities
from fastapi.responses import JSONResponse
from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager
from sqlalchemy.exc import SQLAlchemyError, OperationalError, IntegrityError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import logging
from datetime import datetime,timedelta
from typing import AsyncGenerator

# 圖片加載

# ----------------------------------------------------------------
# 靜態檔案路徑設定 (僅修正此處)
# ----------------------------------------------------------------
# 1. 取得 main.py 當前所在的絕對目錄路徑 (web_app 資料夾)
current_dir = os.path.dirname(os.path.abspath(__file__))

# 2. 拼接出 static 的絕對路徑 (指向同層級的 static 資料夾)
static_dir = os.path.join(current_dir, "static")

# 3. 檢查是否存在 (除錯用)
if os.path.exists(static_dir):
    print(f"✅ 靜態目錄確認: {static_dir}")
else:
    print(f"⚠️ 警告: 找不到目錄 {static_dir}")


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
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
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

    # ==========================
    # 任務 3: 通知自動清理 (新增的部分)
    # ==========================
    # A. 開機檢查 (30秒後 - 錯開其他爬蟲任務)
    scheduler.add_job(
        cleanup_old_notifications,
        "date",
        run_date=datetime.now() + timedelta(seconds=30),
        id="notification_startup_cleanup",
        replace_existing=True
    )

    # B. 定期排程 (每天凌晨 03:00 執行)
    scheduler.add_job(
        cleanup_old_notifications,
        "cron",
        hour=3,
        minute=0,
        id="daily_notification_cleanup",
        replace_existing=True
    )
    # ==========================
    # 任務 4: 登入紀錄自動清理 (解決關機沒執行的問題)
    # ==========================
    # A. 開機檢查 (伺服器一啟動，40秒後立即執行一次)
    # 這樣就算凌晨 03:30 沒開機，你下次打開程式時它還是會幫你清。
    scheduler.add_job(
        cleanup_old_login_activities,
        "date",
        run_date=datetime.now() + timedelta(seconds=40),
        id="login_activity_startup_cleanup",
        replace_existing=True
    )

    # B. 定期排程 (每天凌晨 03:30 執行)
    # 這是給伺服器 24 小時運作時使用的正常維護邏輯。
    scheduler.add_job(
        cleanup_old_login_activities,
        "cron",
        hour=3,
        minute=30,
        id="daily_login_activity_cleanup",
        replace_existing=True
    )


    scheduler.start()
    logging.info("🚀 APScheduler 已啟動 - CPI(6號) & 薪資(20號) 自動更新中,自動刪除超過 30 天以上的登入記錄")

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
  (           )  號
 ( (  )   (  ) )
(__(__)___(__)__).
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

# 1. 讀取 .env
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

# 敏感資訊遮罩工具 (保護隱私)
def mask_sensitive(text: str) -> str:
    if not text: return ""  # 防呆：確保 text 不是 None

    # 遮蓋 SQL 語法或 Token 等敏感關鍵字
    sensitive_patterns = ["password", "token", "secret", "key", "authorization"]
    for word in sensitive_patterns:
        # 使用正則表達式尋找類似 "password": "123" 的結構並遮蓋
        text = re.sub(rf"{word}['\"]?\s*[:=]\s*['\"].*?['\"]", f"{word}: '********'", text, flags=re.IGNORECASE)
    return text

# Discord 錯誤自動通報小工具(非同步背景告警)
def send_discord_alert(message: str, background_tasks: BackgroundTasks, level: str = "ERROR"):
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        return

    # 定義內部的發送邏輯
    async def _async_send():
        emoji = "🚨" if level == "CRITICAL" else "⚠️"
        # 傳出去前先過濾敏感資訊
        safe_message = mask_sensitive(message)
        payload = {"content": f"{emoji} **[Money MMA 報警系統]**\n{safe_message}"}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(webhook_url, json=payload, timeout=5.0)
                if response.status_code == 401:
                    logger.critical("🚨 Discord Webhook URL 已失效 (401)！請更換金鑰。")
                elif response.status_code == 429:
                    retry_after = response.json().get("retry_after", 0)
                    logger.warning(f"Discord 限制中！請等待 {retry_after/1000} 秒。")
                elif response.status_code >= 400:
                    logger.error(f"Discord Webhook 失敗: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Discord 告警失敗: {e}")

    background_tasks.add_task(_async_send)

# 全域通用異常處理器 (萬用防護網)
@app.exception_handler(Exception)
async def universal_handler(request: Request, exc: Exception):
    background_tasks = BackgroundTasks()
    # WebSocket 不回傳 JSON
    if request.scope.get("type") == "websocket":
        logger.warning("WebSocket 異常已攔截")
        return

    # 使用 getattr 並給予預設值 "訪客"，安全性最高
    u_id = getattr(request.state, "user_id_str", "訪客")
    u_name = getattr(request.state, "username_str", "")

    u_info = f"User ID: {u_id} ({u_name})" if u_name else f"User ID: {u_id}"

    logger.error(f"非預期錯誤 User:{u_info} Path:{request.url.path}", exc_info=True)

    error_stack = traceback.format_exc()
    alert = (
        f"❌ **[程式發生崩潰]**\n"
        f"👤 用戶: `{u_info}`\n"
        f"📍 路徑: `{request.method} {request.url.path}`\n"
        f"⚠️ 錯誤: `{str(exc)}`\n"
        f"🔍 Traceback:\n```python\n{error_stack[:800]}\n```"
    )
    send_discord_alert(alert, background_tasks, level="CRITICAL")

    return JSONResponse(
        status_code=500,
        content={"success": False, "detail": "系統發生錯誤，維修人員已收到通知。"},
        background=background_tasks # 將任務掛載到 Response
    )


# 資料庫異常處理器
@app.exception_handler(SQLAlchemyError)
async def db_exception_handler(request: Request, exc: SQLAlchemyError):
    background_tasks = BackgroundTasks()
    # 使用 getattr 並給予預設值 "訪客"，安全性最高
    u_id = getattr(request.state, "user_id_str", "訪客")
    u_name = getattr(request.state, "username_str", "")

    u_info = f"User ID: {u_id} ({u_name})" if u_name else f"User ID: {u_id}"

    prefix, msg = "[DB 一般錯誤]", "資料庫處理異常"
    if isinstance(exc, OperationalError):
        prefix, msg = "🚨 [DB 連線崩潰]", "系統忙碌中，請稍後再試"
    elif isinstance(exc, IntegrityError):
        prefix, msg = "ℹ️ [DB 資料衝突]", "資料重複或格式不符"

    logger.error(f"{prefix} User:{u_info} Path:{request.url.path} Err:{str(exc)}", exc_info=True)

    alert = (
        f"**{prefix}**\n"
        f"👤 用戶: `{u_info}`\n"
        f"📍 路徑: `{request.method} {request.url.path}`\n"
        f"🔍 錯誤: `{str(exc)[:500]}`"
    )
    send_discord_alert(alert, background_tasks, level="CRITICAL") # 背景發送

    return JSONResponse(
        status_code=500,
        content={"success": False, "detail": msg},
        background=background_tasks # 將任務掛載到 Response
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
app.include_router(ai_models.router, prefix="/api/ai_models", tags=["AI模型設定"])
app.include_router(ws.router, prefix="/api/ws", tags=["WebSocket"])
app.include_router(gamification.router, prefix="/api/game",
    tags=["成就系統:每日簽到(checkin)每日任務(missions)成就卡牌(cards)Header摘要(summary)"])
app.include_router(
    admin.router,
    prefix="/api/admin",
    tags=["系統管理後台"],
    dependencies=[Depends(admin_required)],  #  admin/ 底下的所有網址都限管理員
)
app.include_router(analysis.router, prefix="/api/analysis", tags=["消費趨勢分析"])
app.include_router(stats_router, prefix="/api/stats", tags=["圖表分析"])
app.include_router(planning_router, prefix="/api/planning", tags=["理財規劃"])
app.include_router(ai.router,
    prefix="/api/v1/ai",
    tags=["AI 擴充功能"]
)
app.include_router(integrations.router, prefix="/api/integrations", tags=["google行事曆串接"])

@app.get("/favicon.ico", tags=["api圖標"])
async def favicon():
    return RedirectResponse("/static/favicon.ico")


@app.get("/jinja", tags=["jinja 後端頁面呈現檢測用"])
def jinja(request: Request):
    return templates.TemplateResponse(
        request=request, name="test.jinja", context={"第一組": "money"}
    )

# 掛載靜態檔案 (使用上方定義好的 static_dir)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# monitor.py
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import httpx, asyncio, time, logging

from ..database import SessionLocal
from ..models import CpiData, SalaryBenchmark
from ..utils.cpi_crawler import fetch_and_update_cpi
from ..utils.salary_crawler import run_all_salary_tasks
from sqlalchemy import func
# 薪資發布通常比 CPI 晚，允許落後 1 個月不算異常
#from datetime import datetime, timedelta
import os
from sqlalchemy import text

router = APIRouter()
logger = logging.getLogger(__name__)

# ── 被監控的外部金融 API 清單 ────────────────────────────────────
WATCHED_APIS = [
    # monitor.py 的 WATCHED_APIS 補上這三條

{
    "name": "Groq API",
    "url": "https://api.groq.com/openai/v1/models",
    "desc": "LLM 推理・語音辨識・LangGraph",
    "category": "ai",
},
{
    "name": "Gemini API",
    "url": "https://generativelanguage.googleapis.com/v1beta/models",
    "desc": "主要 LLM・圖片辨識・收據解析",
    "category": "ai",
},
{
    "name": "LINE Messaging API",
    "url": "https://api.line.me/v2/bot/info",
    "desc": "LINE Bot 聊天・語音・記帳",
    "category": "bot",
},
    
    
    {
        "name": "台灣銀行匯率",
        "url": "https://rate.bot.com.tw/xrt/flcsv/0/day",
        "desc": "免費・無需 API key",
        "category": "exchange",
    },
    {
        "name": "TWSE 台灣證交所",
        "url": "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
        "desc": "免費・股票行情",
        "category": "stock",
    },
    {
        "name": "行政院主計總處",
    "url": "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230555/pr0101a1m.xml",
    "desc": "免費・CPI XML 資料源",
    "category": "gov",
    },
    {
        "name": "金管會 FSC Open Data",
        "url": "https://opendata.fsc.gov.tw/",
        "desc": "免費・金融商品",
        "category": "gov",
    },
    {
        "name": "財政部資料開放平台",
        "url": "https://data.mof.gov.tw/",
        "desc": "免費・稅務統計",
        "category": "gov",
    },
]

# ── 快取（避免每次前端刷新都重打外部 API）───────────────────────
_health_cache: dict = {"ts": 0, "data": []}
CACHE_TTL = 60  # 秒


# ── 1. 排程任務清單 ───────────────────────────────────────────────
@router.get("/jobs")
def get_jobs(request: Request):
    scheduler = getattr(request.app.state, "scheduler", None)
    if not scheduler:
        return JSONResponse({"error": "排程器未啟動"}, status_code=503)

    jobs = []
    for job in scheduler.get_jobs():
        jobs.append(
            {
                "id": job.id,
                "name": job.name or job.id,
                "next_run": str(job.next_run_time) if job.next_run_time else "等待中",
                "trigger": str(job.trigger),
                "func": str(job.func.__name__) if hasattr(job.func, "__name__") else str(job.func),
            }
        )
    return {"total": len(jobs), "jobs": jobs}


# ── 2. 外部 API 健康檢查 ──────────────────────────────────────────
@router.get("/api-health")
async def check_api_health(force: bool = False):
    global _health_cache
    now = time.time()

    # 未過快取時間直接回傳
    if not force and now - _health_cache["ts"] < CACHE_TTL and _health_cache["data"]:
        return {"cached": True, "ts": _health_cache["ts"], "apis": _health_cache["data"]}

    async with httpx.AsyncClient(timeout=6.0) as client:
        results = await asyncio.gather(*[_ping(client, api) for api in WATCHED_APIS])

    _health_cache = {"ts": now, "data": list(results)}
    return {"cached": False, "ts": now, "apis": list(results)}


# ── 3. 自身路由清單（內部健康自檢）──────────────────────────────
@router.get("/routes")
def get_routes(request: Request):
    routes = []
    for route in request.app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            routes.append(
                {
                    "path": route.path,
                    "methods": sorted(route.methods),
                    "name": route.name or "",
                    "tags": getattr(route, "tags", []),
                }
            )
    return {"total": len(routes), "routes": sorted(routes, key=lambda r: r["path"])}


# ── 工具：ping 單一 API ───────────────────────────────────────────
async def _ping(client: httpx.AsyncClient, api: dict) -> dict:
    start = time.time()
    try:
        # 用 HEAD 最省流量，部分 API 不支援時改 GET
        try:
            r = await client.head(api["url"])
        except Exception:
            r = await client.get(api["url"])

        ms = int((time.time() - start) * 1000)
        code = r.status_code

        if code < 400:
            status = "ok" if ms < 1000 else "warn"
        else:
            status = "warn" if code < 500 else "fail"

        return {**api, "status": status, "ms": ms, "code": code}

    except httpx.TimeoutException:
        ms = int((time.time() - start) * 1000)
        return {**api, "status": "fail", "ms": ms, "code": None, "error": "timeout"}
    except Exception as e:
        ms = int((time.time() - start) * 1000)
        logger.warning(f"[monitor] ping 失敗 {api['name']}: {e}")
        return {**api, "status": "fail", "ms": ms, "code": None, "error": str(e)[:80]}
    
    
    
    
# ── 4. CPI 爬蟲狀態 ───────────────────────────────────────────────
@router.get("/cpi-status")
def get_cpi_status():
    """回傳資料庫中 CPI 資料的最新狀態與筆數"""
    with SessionLocal() as db:
        latest = (
            db.query(CpiData)
            .order_by(CpiData.period.desc())
            .first()
        )
        total = db.query(func.count(CpiData.cpi_id)).scalar()
        categories = db.query(func.count(func.distinct(CpiData.category))).scalar()

        from datetime import datetime, timedelta
        current_date = datetime.now()
        two_months_ago = (current_date.replace(day=1) - timedelta(days=1))
        two_months_ago = (two_months_ago.replace(day=1) - timedelta(days=1)).strftime("%YM%m")


        is_fresh = latest and latest.period >= two_months_ago

        return {
            "source_url": "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230555/pr0101a1m.xml",
            "source_name": "行政院主計總處 DGBAS",
            "latest_period": latest.period if latest else None,
            "expected_period": two_months_ago,
            "is_fresh": is_fresh,               # True = 資料是最新的
            "status": "ok" if is_fresh else "warn",
            "total_rows": total,
            "category_count": categories,
        }


# ── 5. 薪資爬蟲狀態 ───────────────────────────────────────────────
@router.get("/salary-status")
def get_salary_status():
    """回傳兩種薪資類型各自的最新狀態"""
    from datetime import datetime, timedelta
    current_date = datetime.now()
    two_months_ago = (current_date.replace(day=1) - timedelta(days=1))
    two_months_ago = (two_months_ago.replace(day=1) - timedelta(days=1)).strftime("%YM%m")


    salary_types = ["經常性薪資", "總薪資"]
    results = []

    with SessionLocal() as db:
        for salary_type in salary_types:
            latest = (
                db.query(SalaryBenchmark)
                .filter(SalaryBenchmark.salary_type == salary_type)
                .order_by(SalaryBenchmark.period.desc())
                .first()
            )
            count = (
                db.query(func.count(SalaryBenchmark.salary_id))
                .filter(SalaryBenchmark.salary_type == salary_type)
                .scalar()
            )
            is_fresh = latest and latest.period >= two_months_ago
            results.append({
                "salary_type": salary_type,
                "latest_period": latest.period if latest else None,
                "expected_period": two_months_ago,
                "is_fresh": is_fresh,
                "status": "ok" if is_fresh else "warn",
                "total_rows": count,
            })

    overall = "ok" if all(r["is_fresh"] for r in results) else "warn"
    return {
        "source_url": "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230037/",
        "source_name": "行政院主計總處 薪資統計",
        "overall_status": overall,
        "types": results,
    }


# ── 6. 手動觸發爬蟲（開發 / 緊急用）────────────────────────────
@router.post("/trigger-crawl")
async def trigger_crawl(task: str = "cpi"):
    """
    手動觸發單次爬蟲（不影響排程）
    task 參數: "cpi" | "salary"
    """
    if task not in ("cpi", "salary"):
        return JSONResponse({"error": "task 只接受 cpi 或 salary"}, status_code=400)

    try:
        if task == "cpi":
            await asyncio.to_thread(fetch_and_update_cpi)
            return {"triggered": "cpi", "message": "CPI 爬蟲執行完畢，請查看 /api/monitor/cpi-status"}
        else:
            await asyncio.to_thread(run_all_salary_tasks)
            return {"triggered": "salary", "message": "薪資爬蟲執行完畢，請查看 /api/monitor/salary-status"}
    except Exception as e:
        logger.error(f"[monitor] 手動觸發爬蟲失敗: {e}", exc_info=True)
        return JSONResponse({"error": str(e)[:200]}, status_code=500)



# monitor.py 新增這個 endpoint
@router.get("/ollama-status")
async def check_ollama_status():
    """檢查地端 Ollama 是否運行中"""
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{base_url}/api/tags")
            ms = int((time.time() - start) * 1000)
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                return {"status": "ok", "ms": ms, "models": models, "count": len(models)}
            return {"status": "fail", "ms": ms, "code": r.status_code}
    except Exception as e:
        return {"status": "fail", "ms": int((time.time() - start)*1000), "error": str(e)[:80]}
    

@router.get("/task-history")
def get_task_history(task: str = "cpi", limit: int = 20):
    """查看爬蟲歷史執行紀錄"""
    from ..models import TaskRunLog
    with SessionLocal() as db:
        logs = (
            db.query(TaskRunLog)
            .filter(TaskRunLog.task_name == task)
            .order_by(TaskRunLog.ran_at.desc())
            .limit(limit)
            .all()
        )
        return {
            "task": task,
            "logs": [
                {
                    "status": l.status,
                    "rows_added": l.rows_added,
                    "rows_updated": l.rows_updated,
                    "message": l.message,
                    "ran_at": str(l.ran_at),
                }
                for l in logs
            ]
        }
        
# ChromaDB 向量庫統計
@router.get("/vectordb-stats")
def get_vectordb_stats():
    """查看 ChromaDB 各 collection 的文件數量"""
    try:
        import chromadb
        client = chromadb.PersistentClient(path="./.chromadb")
        collections = client.list_collections()
        result = {}
        for col in collections:
            result[col.name] = col.count()
        return {"status": "ok", "collections": result}
    except Exception as e:
        return {"status": "fail", "error": str(e)[:100]}


# 資料庫連線狀態
@router.get("/db-status")
def get_db_status():
    start = time.time()
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        ms = int((time.time() - start) * 1000)
        return {"status": "ok", "ms": ms}
    except Exception as e:
        return {"status": "fail", "error": str(e)[:100]}



@router.get("/schema-checklist")
def get_schema_checklist():
    """列出所有 ORM 模型的資料表名稱，方便對照 schema_collection.md 是否同步"""
    from ..database import Base
    tables = sorted(Base.metadata.tables.keys())
    return {
        "total": len(tables),
        "tables": tables,
        "reminder": "請確認以上所有表格都已更新到 web_app/data/secret/schema_collection.md"
    }

    
# 統計摘要:錯跟警告
@router.get("/log-summary")
def get_log_summary():
    """統計今日錯誤與警告數量，不暴露原始 log 內容"""
    from datetime import date
    log_path = os.getenv("LOG_FILE", "logs/app.log")
    today_str = date.today().strftime("%Y-%m-%d")
    
    counts = {"ERROR": 0, "CRITICAL": 0, "WARNING": 0}
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                if today_str not in line:
                    continue
                for level in counts:
                    if level in line:
                        counts[level] += 1
    except FileNotFoundError:
        pass
    
    return {"date": today_str, **counts,
            "has_critical": counts["CRITICAL"] > 0}

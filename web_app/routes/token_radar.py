# routers/token_radar.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional
from datetime import datetime, timedelta
from web_app.dependencies import get_current_user
from ..database import get_db
from ..models import TokenUsageLog
from ..schemas.token_radar import (
    TokenRadarSummary, TokenLogListOut, TokenUsageLogOut,
    ProviderStat, IntentStat, QuotaWarning, TokenUsageCreate
)
# 如果你有 JWT 驗證中間件，換成你自己的
# from ..dependencies import get_current_user
router = APIRouter()

# ── 工具函式：根據 date_range 算出起始時間 ─────────────────────
def _get_start_dt(date_range: str) -> Optional[datetime]:
    now = datetime.now()
    if date_range == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif date_range == "week":
        return now - timedelta(days=7)
    elif date_range == "month":
        return now - timedelta(days=30)
    return None  # all


# ── 免費額度設定（可之後改為從 DB 讀取）────────────────────────
FREE_QUOTAS = {
    "gemini":  {"model": "gemini-2.0-flash",  "limit": 1_000_000},  # 每月免費額度(token)
    "groq":    {"model": "llama3-70b-8192",   "limit": 500_000},    # 粗估每月
}


# ── GET /api/token-radar/summary ──────────────────────────────
@router.get("/summary", response_model=TokenRadarSummary)
def get_summary(
    date_range: str = Query("today", enum=["today", "week", "month", "all"]),
    provider: Optional[str] = None,
    db: Session = Depends(get_db),
    # current_user = Depends(get_current_user),  # 開啟驗證時取消注解
):
    start_dt = _get_start_dt(date_range)
    q = db.query(TokenUsageLog)
    if start_dt:
        q = q.filter(TokenUsageLog.created_at >= start_dt)
    if provider:
        q = q.filter(TokenUsageLog.provider == provider)

    all_logs = q.all()
    if not all_logs:
        return TokenRadarSummary(
            period_tokens=0, period_requests=0,
            avg_tokens_per_req=0, max_single_tokens=0,
            max_single_intent=None, by_provider=[], by_intent=[]
        )

    period_tokens   = sum(l.total_tokens for l in all_logs)
    period_requests = len(all_logs)
    avg_tpr = round(period_tokens / period_requests, 1) if period_requests else 0

    # 單次最高
    max_log = max(all_logs, key=lambda l: l.total_tokens)

    # 廠商分佈
    provider_map: dict[str, dict] = {}
    for l in all_logs:
        p = l.provider
        if p not in provider_map:
            provider_map[p] = {"tokens": 0, "requests": 0}
        provider_map[p]["tokens"]   += l.total_tokens
        provider_map[p]["requests"] += 1
    by_provider = [
        ProviderStat(provider=k, tokens=v["tokens"], requests=v["requests"])
        for k, v in sorted(provider_map.items(), key=lambda x: -x[1]["tokens"])
    ]

    # 意圖分佈
    intent_map: dict[str, int] = {}
    for l in all_logs:
        intent_map[l.intent_type] = intent_map.get(l.intent_type, 0) + l.total_tokens
    by_intent = [
        IntentStat(
            intent_type=k, tokens=v,
            pct=round(v / period_tokens * 100, 1) if period_tokens else 0
        )
        for k, v in sorted(intent_map.items(), key=lambda x: -x[1])
    ]

    # 額度預警（只統計本月）
    month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0)
    quota_warnings = []
    for prov, cfg in FREE_QUOTAS.items():
        used = db.query(func.sum(TokenUsageLog.total_tokens)).filter(
            TokenUsageLog.provider == prov,
            TokenUsageLog.created_at >= month_start
        ).scalar() or 0
        pct = round(used / cfg["limit"] * 100, 1) if cfg["limit"] else 0
        quota_warnings.append(QuotaWarning(
            provider=prov, model=cfg["model"],
            used=used, limit=cfg["limit"], pct=pct
        ))

    return TokenRadarSummary(
        period_tokens=period_tokens,
        period_requests=period_requests,
        avg_tokens_per_req=avg_tpr,
        max_single_tokens=max_log.total_tokens,
        max_single_intent=max_log.intent_type,
        by_provider=by_provider,
        by_intent=by_intent,
        quota_warnings=quota_warnings,
    )


# ── GET /api/token-radar/logs ─────────────────────────────────
@router.get("/logs", response_model=TokenLogListOut)
def get_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(15, ge=1, le=100),
    date_range: str = Query("today", enum=["today", "week", "month", "all"]),
    provider: Optional[str] = None,
    intent_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    start_dt = _get_start_dt(date_range)
    q = db.query(TokenUsageLog)
    if start_dt:
        q = q.filter(TokenUsageLog.created_at >= start_dt)
    if provider:
        q = q.filter(TokenUsageLog.provider == provider)
    if intent_type:
        q = q.filter(TokenUsageLog.intent_type == intent_type)

    total = q.count()
    logs = q.order_by(desc(TokenUsageLog.created_at)) \
             .offset((page - 1) * limit).limit(limit).all()

    return TokenLogListOut(
        logs=[TokenUsageLogOut.model_validate(l) for l in logs],
        total=total, page=page, limit=limit
    )


# ── POST /api/token-radar/log（內部呼叫，Service 層用）─────────
@router.post("/log", status_code=201)
def create_log(payload: TokenUsageCreate, db: Session = Depends(get_db)):
    """由 GeminiService / GroqService 直接呼叫，不對外暴露給前端"""
    # 只取 request_snippet 前 500 字，防止塞爆 DB
    snippet = payload.request_snippet
    if snippet and len(snippet) > 500:
        snippet = snippet[:500] + "..."

    log = TokenUsageLog(
        user_id=payload.user_id,
        provider=payload.provider,
        model_version=payload.model_version,
        intent_type=payload.intent_type,
        prompt_tokens=payload.prompt_tokens,
        completion_tokens=payload.completion_tokens,
        total_tokens=payload.total_tokens,
        latency_ms=payload.latency_ms,
        is_cached=payload.is_cached,
        error_code=payload.error_code,
        request_snippet=snippet,
    )
    db.add(log)
    db.commit()
    return {"status": "ok", "log_id": log.log_id}
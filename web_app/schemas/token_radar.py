# schemas/token_radar.py
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ── 寫入用（Service 層呼叫，不需要 user 手動填）──────────────
class TokenUsageCreate(BaseModel):
    user_id: int
    provider: str                       # gemini / groq / openai / ollama
    model_version: str
    intent_type: str = "UNKNOWN"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: Optional[int] = None
    is_cached: bool = False
    error_code: Optional[str] = None
    request_snippet: Optional[str] = None  # 只取前 500 字


# ── 回傳用（前端讀取 log 列表）───────────────────────────────
class TokenUsageLogOut(BaseModel):
    log_id: int
    provider: str
    model_version: str
    intent_type: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: Optional[int]
    is_cached: bool
    created_at: datetime
    request_snippet: Optional[str] = None

    class Config:
        from_attributes = True


# ── 廠商分佈統計 ──────────────────────────────────────────────
class ProviderStat(BaseModel):
    provider: str
    tokens: int
    requests: int


# ── 意圖分佈統計 ──────────────────────────────────────────────
class IntentStat(BaseModel):
    intent_type: str
    tokens: int
    pct: float          # 佔比百分比，後端算好


# ── 額度預警 (可選，預設閾值寫死或從 ai_configs 讀) ────────────
class QuotaWarning(BaseModel):
    provider: str
    model: str
    used: int
    limit: int
    pct: float


# ── 儀表板彙總回傳 ────────────────────────────────────────────
class TokenRadarSummary(BaseModel):
    period_tokens: int          # 區間內總 Token
    period_requests: int        # 區間內總請求數
    avg_tokens_per_req: float   # 平均每次消耗
    max_single_tokens: int      # 單次最高消耗
    max_single_intent: Optional[str]  # 最高消耗的意圖類型
    by_provider: List[ProviderStat]
    by_intent: List[IntentStat]
    quota_warnings: List[QuotaWarning] = []


# ── 分頁 Log 列表回傳 ─────────────────────────────────────────
class TokenLogListOut(BaseModel):
    logs: List[TokenUsageLogOut]
    total: int
    page: int
    limit: int
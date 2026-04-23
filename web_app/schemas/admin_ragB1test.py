from pydantic import BaseModel
from typing import Optional
from decimal import Decimal

# 1. 實驗檢索請求
class RagTestRequest(BaseModel):
    query: str
    hnsw_m: int = 16
    hnsw_ef: int = 100
    top_k: int = 5

# 2. 效能日誌儲存
class RagLogCreate(BaseModel):
    query_text: str
    hnsw_m: int
    hnsw_ef: int
    retrieval_ms: int
    llm_duration_s: Decimal
    tokens_per_sec: Decimal
    vram_usage_mb: int
    gpu_temp: int
    total_chunks: int
    human_score: int
    ai_response: str
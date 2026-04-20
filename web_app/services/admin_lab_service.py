# web_app/services/admin_lab_service.py
import time
import random
from decimal import Decimal
from .ollama_service import OllamaService
from .vector_db_tools import VectorDBTools

class AdminLabService:
    @staticmethod
    async def run_rag_performance_test(query: str, hnsw_m: int, hnsw_ef: int, top_k: int):
        # 1. 測量檢索延遲
        start_time = time.time()
        vectorstore = VectorDBTools.get_codebase_store()
        
        # 🌟 透過 search_kwargs 注入實驗參數
        docs = vectorstore.similarity_search(
            query[:1000], 
            k=top_k,
            search_kwargs={"k": top_k, "ef_search": hnsw_ef}
        )
        retrieval_ms = int((time.time() - start_time) * 1000)

        # 2. 組合 Context
        context = "\n".join([f"--- {doc.metadata.get('source')} ---\n{doc.page_content}" for doc in docs])

        # 3. 測量 LLM 生成效能 (補上 base_url 解決妳的紅線問題)
        llm_start = time.time()
        response_text = await OllamaService.chat_async(
            base_url="http://localhost:11434", # 🌟 補齊參數
            model_id="gemma4:e4b",
            prompt=f"【參考代碼】:\n{context}\n\n【問題】: {query}",
            system_instruction="你是一個資深的系統架構師，請根據代碼回答問題。"
        )
        llm_duration_s = time.time() - llm_start
        
        # 4. 計算推論速度 (TPS)
        tokens_per_sec = len(response_text) / llm_duration_s if llm_duration_s > 0 else 0

        return {
            "ai_response": response_text,
            "retrieval_ms": retrieval_ms,
            "llm_duration_s": round(Decimal(llm_duration_s), 2),
            "tokens_per_sec": round(Decimal(tokens_per_sec), 2),
            "total_chunks": 3452  # 這裡可以之後做動態 count
        }

    @staticmethod
    def get_gpu_status():
        """獲取硬體監控數據 (RTX 4060 Ti)"""
        # 這裡未來可以用 nvidia-smi 真正抓取，目前先給予動態模擬值
        return {
            "gpu_temp": random.randint(40, 52),
            "vram_usage": random.randint(2100, 3500),
            "load": random.randint(5, 15)
        }
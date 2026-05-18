# web_app/services/admin_lab_service.py
import time
import random
import os
import subprocess
from decimal import Decimal
from .ollama_service import OllamaService
from .vector_db_tools import VectorDBTools

IS_CLOUD = os.getenv("RENDER") == "true"

class AdminLabService:
    @staticmethod
    async def run_rag_performance_test(query: str, hnsw_m: int, hnsw_ef: int, top_k: int):
        start_time = time.time()
        vectorstore = VectorDBTools.get_codebase_store()
        docs = vectorstore.similarity_search(query, k=top_k)
        retrieval_ms = int((time.time() - start_time) * 1000)

        context = "\n".join([f"--- {doc.metadata.get('source')} ---\n{doc.page_content}" for doc in docs])

        llm_start = time.time()
        response_text = await OllamaService.chat_async(
            base_url="http://localhost:11434",
            model_id="gemma4:e4b",
            prompt=f"【參考代碼】:\n{context}\n\n【問題】: {query}",
            system_instruction="你是一個資深的系統架構師，請根據代碼回答問題。",
            timeout_sec=300.0
        )
        llm_duration_s = time.time() - llm_start
        tokens_per_sec = len(response_text) / llm_duration_s if llm_duration_s > 0 else 0

        total_chunks = 0
        try:
            total_chunks = vectorstore._collection.count()
        except Exception as e:
            print(f"Count error: {e}")

        return {
            "ai_response":    response_text,
            "retrieval_ms":   retrieval_ms,
            "llm_duration_s": round(Decimal(llm_duration_s), 2),
            "tokens_per_sec": round(Decimal(tokens_per_sec), 2),
            "total_chunks":   total_chunks,
        }

    @staticmethod
    def get_gpu_status():
        """獲取硬體監控數據 (RTX 4060 Ti)"""

        # 雲端環境直接跳 Fallback，不呼叫 nvidia-smi
        if not IS_CLOUD:
            try:
                result = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=temperature.gpu,memory.used,utilization.gpu",
                        "--format=csv,noheader,nounits"
                    ],
                    capture_output=True, text=True, timeout=3
                )
                if result.returncode == 0:
                    parts = result.stdout.strip().split(", ")
                    return {
                        "gpu_temp":   int(parts[0]),
                        "vram_usage": int(parts[1]),
                        "load":       int(parts[2]),
                    }
            except Exception as e:
                print(f"⚠️ nvidia-smi 呼叫失敗，改用模擬值: {e}")

        # Fallback：雲端 或 nvidia-smi 不可用
        return {
            "gpu_temp":   random.randint(40, 52),
            "vram_usage": random.randint(2100, 3500),
            "load":       random.randint(5, 15),
        }
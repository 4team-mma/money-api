# web_app/utils/ai_warmup.py
import logging
import asyncio
import httpx

logger = logging.getLogger(__name__)

async def warmup_ai_systems():
    logger.info("🔥 [系統預熱] 開始執行背景熱機程序...")

    # 1. 預熱意圖分類引擎與詞庫 (雲端與地端都需要，因為這是載入 Jieba)
    try:
        from web_app.services.finance_agent_mixai_service import FinanceAgentMixAIService
        # 隨便丟一句廢話讓它觸發載入
        FinanceAgentMixAIService.analyze_intent("預熱測試")
        logger.info("✅ [預熱完成] 意圖分類器與 Jieba 詞庫已載入")
    except Exception as e:
        logger.warning(f"⚠️ 意圖分類器預熱失敗: {e}")

    # 2. 預熱 RAG 向量與重排引擎 (雲端與地端都需要，因為要載入 HuggingFace 模型)
    try:
        from web_app.services.vector_db_tools import VectorDBTools
        # 隨便搜一個詞觸發 HuggingFace 和 Cohere
        VectorDBTools.search_manual("預熱")
        logger.info("✅ [預熱完成] HuggingFace 向量搜尋與 Cohere 引擎已載入")
    except Exception as e:
        logger.warning(f"⚠️ RAG 引擎預熱失敗: {e}")

    # 3. 預熱地端 LLM (只針對 Ollama)
    try:
        # 先輕輕戳一下本地的 Ollama 看看他有沒有活著
        async with httpx.AsyncClient() as client:
            res = await client.get("http://localhost:11434/api/tags", timeout=3.0)
            
            if res.status_code == 200:
                logger.info("🔥 偵測到地端 Ollama 運作中，開始將模型載入顯示卡記憶體...")
                # 發送一個極短的廢話，強迫 Ollama 把 gemma3:4b 拉進 VRAM
                payload = {
                    "model": "gemma3:4b", # 如果你的預設模型名字不同，請改這裡
                    "prompt": "hi",
                    "stream": False
                }
                # 給他 60 秒的時間慢慢搬進顯示卡
                await client.post("http://localhost:11434/api/generate", json=payload, timeout=60.0)
                logger.info("✅ [預熱完成] Ollama 模型已成功載入顯存！")
                
    except httpx.ConnectError:
        # 如果是連不上 localhost:11434 (例如部署在雲端 Render 上)，就會跑到這裡
        logger.info("⏭️ [預熱跳過] 未偵測到本地 Ollama 或身處雲端，無需預熱大模型。")
    except Exception as e:
        logger.warning(f"⚠️ Ollama 預熱發生未預期錯誤: {e}")

    logger.info("🚀 [系統預熱] 所有背景熱機作業結束！")
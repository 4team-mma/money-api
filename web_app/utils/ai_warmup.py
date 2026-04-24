# web_app/utils/ai_warmup.py
import logging
import httpx
import os

logger = logging.getLogger(__name__)

async def warmup_ai_systems():
    logger.info("🔥 [系統預熱] 開始執行背景熱機程序...")

    # 1. 預熱意圖分類引擎與詞庫 (載入 Jieba)
    try:
        from web_app.services.finance_agent_mixai_service import FinanceAgentMixAIService
        # 隨便丟一句廢話讓它觸發載入
        FinanceAgentMixAIService.analyze_intent("預熱測試")
        logger.info("✅ [預熱完成] 意圖分類器與 Jieba 詞庫已載入")
    except Exception as e:
        logger.warning(f"⚠️ 意圖分類器預熱失敗: {e}")

    # 2. 2. 預熱 RAG 向量引擎（雲端跳過，讓模型在第一次請求時懶載入）
    if os.getenv("IS_CLOUD", "false").lower() != "true":
        try:
            from web_app.services.vector_db_tools import VectorDBTools
            VectorDBTools.search_manual("預熱")
            logger.info("✅ [預熱完成] FastEmbed 地端向量搜尋引擎已載入")
        except Exception as e:
            logger.warning(f"⚠️ RAG 引擎預熱失敗: {e}")
    else:
        logger.info("⏭️ [預熱跳過] 雲端環境，FastEmbed 將在首次請求時懶載入")

    # 3. 預熱地端 LLM (只針對 Ollama)
    try:
        # 先輕輕戳一下本地的 Ollama 看看他有沒有活著
        async with httpx.AsyncClient() as client:
            # 這裡使用超短 Timeout，因為身處雲端時一定會連不上
            res = await client.get("http://localhost:11434/api/tags", timeout=1.0)
            
            if res.status_code == 200:
                logger.info("🔥 偵測到地端 Ollama 運作中，開始將模型載入顯示卡記憶體...")
                # 發送一個極短的廢話，強迫 Ollama 把 gemma3:4b 拉進 VRAM
                payload = {
                    "model": "gemma3:4b", 
                    "prompt": "hi",
                    "stream": False
                }
                # 給它 60 秒的時間慢慢搬進顯示卡
                await client.post("http://localhost:11434/api/generate", json=payload, timeout=60.0)
                logger.info("✅ [預熱完成] Ollama 模型已成功載入顯存！")
                
    except (httpx.ConnectError, httpx.TimeoutException):
        # 如果連不上 (例如部署在雲端 Render 上)，就跳過
        logger.info("⏭️ [預熱跳過] 未偵測到本地 Ollama 或身處雲端，無需預熱大模型。")
    except Exception as e:
        logger.warning(f"⚠️ Ollama 預熱發生未預期錯誤: {e}")

    logger.info("🚀 [系統預熱] 所有背景熱機作業結束！")
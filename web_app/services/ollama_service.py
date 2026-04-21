# web_app/services/ollama_service.py
import httpx
import logging

logger = logging.getLogger(__name__)

class OllamaService:
    @staticmethod
    async def chat_async(base_url: str, model_id: str, prompt: str, system_instruction: str):
        """處理 Ollama 本地模型對話"""
        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "model": model_id,
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": prompt}
                    ],
                    "stream": False,
                    "options": {
                        "temperature": 0.2,  # 降低隨機性，讓它乖乖看數據
                        "num_ctx": 4096      # 確保上下文夠長
                    }
                }

                logger.info(f"Ollama Request: {base_url} | Model: {model_id}")

                res = await client.post(
                    f"{base_url}/api/chat",
                    json=payload,
                    # 原本120.0
                    #timeout=300.0
                    timeout=httpx.Timeout(60.0, connect=5.0)
                )

                if res.status_code == 200:
                    return res.json()["message"]["content"]
                else:
                    err_text = res.text
                    logger.error(f"Ollama Error {res.status_code}: {err_text}")
                    return f"喵... Ollama 連線錯誤 (Status: {res.status_code})"

        except Exception as e:
            logger.error(f"Ollama Connection Error: {str(e)}")
            return f"喵... 呼叫地端模型失敗，請確認 Ollama 有開喵: {str(e)[:50]}"


    @staticmethod
    async def chat_stream_async(base_url: str, model_id: str, prompt: str, system_instruction: str):
        from langchain_community.llms import Ollama
        llm = Ollama(base_url=base_url, model=model_id, system=system_instruction)
        async for chunk in llm.astream(prompt):
            yield chunk
# web_app/services/llava_service.py
import httpx
import base64
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class LLaVAService:

    @staticmethod
    def encode_image_to_base64(image_bytes: bytes) -> str:
        """將圖片 bytes 轉成 base64 字串"""
        return base64.b64encode(image_bytes).decode("utf-8")

    @staticmethod
    async def parse_receipt_image(base_url: str, model_id: str, image_bytes: bytes) -> dict:
        """
        用 LLaVA 解析訂單截圖，回傳結構化 JSON
        只有在使用者上傳圖片時才會被呼叫
        """
        image_b64 = LLaVAService.encode_image_to_base64(image_bytes)

        system_prompt = """你是一個訂單解析助手。
請分析圖片中的訂單資訊，並**只回傳 JSON 格式**，不要有任何多餘文字。
格式如下：
{
  "store": "店名",
  "add_amount": 總金額數字,
  "add_class": "飲食",
  "add_note": "店名 訂單",
  "items": [
    {"item_name": "品項名稱", "item_amount": 金額數字, "item_class": "飲食"},
    {"item_name": "外送費",   "item_amount": 金額數字, "item_class": "服務費"}
  ]
}
注意：add_amount 必須等於所有 items 的 item_amount 總和。"""

        payload = {
            "model": model_id,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": f"data:image/jpeg;base64,{image_b64}"
                        },
                        {
                            "type": "text",
                            "text": "請解析這張訂單截圖"
                        }
                    ]
                }
            ],
            "stream": False,
            "options": {
                "temperature": 0.1  # 解析任務要非常穩定
            }
        }

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=5.0)) as client:
                res = await client.post(f"{base_url}/api/chat", json=payload)

                if res.status_code != 200:
                    logger.error(f"LLaVA Error {res.status_code}: {res.text}")
                    return {"error": f"LLaVA 連線失敗 (Status: {res.status_code})"}

                raw_text = res.json()["message"]["content"]
                logger.info(f"LLaVA raw output: {raw_text}")

                # 解析 JSON，處理 LLaVA 可能夾帶 markdown 的情況
                return LLaVAService._safe_parse_json(raw_text)

        except Exception as e:
            logger.error(f"LLaVA Service Error: {str(e)}")
            return {"error": f"圖片解析失敗：{str(e)[:80]}"}

    @staticmethod
    def _safe_parse_json(raw_text: str) -> dict:
        """
        安全解析 LLaVA 輸出，處理可能包含 ```json ``` 的情況
        """
        import json
        import re

        # 嘗試直接 parse
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            pass

        # 嘗試抓 ```json ... ``` 區塊
        match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw_text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        logger.warning(f"無法解析 LLaVA 輸出: {raw_text[:200]}")
        return {"error": "無法解析圖片內容，請手動輸入"}
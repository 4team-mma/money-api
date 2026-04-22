# web_app/services/llava_service.py
import httpx
import base64
import logging
import pynvml  # ✅ 1. 引入 pynvml

logger = logging.getLogger(__name__)

# ✅ 設定集中在這裡，routes 不需要知道
LLAVA_BASE_URL = "http://localhost:11434"
LLAVA_MODEL = "llava-phi3"

class LLaVAService:

    @staticmethod
    def encode_image_to_base64(image_bytes: bytes) -> str:
        """將圖片 bytes 轉成 base64 字串"""
        return base64.b64encode(image_bytes).decode("utf-8")

    @staticmethod
    async def parse_receipt_image(image_bytes: bytes) -> dict:
        """
        用 LLaVA 解析訂單截圖，回傳結構化 JSON
        只有在使用者上傳圖片時才會被呼叫
        """
        image_b64 = LLaVAService.encode_image_to_base64(image_bytes)

        system_prompt = """
        
        你是訂單 OCR 解析器。
規則：
1. 只擷取「品項名稱」和「該品項金額」，忽略折扣、優惠券、服務費
2. add_amount = 總計（含稅）的數字
3. 如果有「- $xx」折扣行，不要列為品項
4. 回傳純 JSON，不要解釋
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
    "model": LLAVA_MODEL,   # ← 用常數，不用參數
    "messages": [
        {
            "role": "user",
            "content": system_prompt + "\n\n請解析這張訂單截圖",  # ← 純字串
            "images": [image_b64]  # ← base64，不加 data:image/jpeg;base64, 前綴
        }
    ],
    "stream": False,
    "options": {
        "temperature": 0.1
    }
}

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=5.0)) as client:
                res = await client.post(f"{LLAVA_BASE_URL}/api/chat", json=payload)

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
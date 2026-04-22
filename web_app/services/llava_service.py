# web_app/services/llava_service.py
import httpx
import base64
import logging
import pynvml  

logger = logging.getLogger(__name__)

# ✅ 設定集中在這裡，routes 不需要知道
LLAVA_BASE_URL = "http://localhost:11434"
# LLAVA_MODEL = "llava-phi3"  # ← 原本寫死的註解掉，改用動態取得

class LLaVAService:

    @staticmethod
    def _get_dynamic_model() -> str:
        """
        [新增] 動態檢查 GPU VRAM。
        為了測試穩定性，將門檻設為 15GB，確保 8GB 顯卡一定會跑 4b 模型。
        """
        try:
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            free_bytes = int(info.free)  # type: ignore
            free_vram_gb = free_bytes / (1024 ** 3)
            pynvml.nvmlShutdown()

            # 將門檻設高（例如 15.0），強制讓 8GB 顯卡走 else 路徑載入 4b
            if free_vram_gb > 15.0:
                logger.info(f"📊 [VRAM 監控] 剩餘顯存: {free_vram_gb:.2f} GB -> 資源極其充足，載入 qwen3-vl:8b")
                return "qwen3-vl:8b"
            else:
                logger.info(f"📊 [VRAM 監控] 剩餘顯存: {free_vram_gb:.2f} GB -> 測試模式，載入 qwen3-vl:4b")
                return "qwen3-vl:4b"
        except Exception as e:
            logger.warning(f"📊 [VRAM 監控] 無法讀取 VRAM，預設安全使用 qwen3-vl:4b。錯誤: {e}")
            return "qwen3-vl:4b"

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
        
        # ✅ 2. 呼叫動態模型選擇器
        target_model = LLaVAService._get_dynamic_model()

        system_prompt = """

你是訂單 OCR 解析器。

⚠️ 你必須只輸出「合法 JSON」，不能包含任何說明、標點或多餘文字。
⚠️ 不允許出現 ```json 或任何 markdown

格式：
{
  "store": "...",
  "add_amount": 數字,
  "add_class": "飲食",
  "add_note": "...",
  "items": [
    {"item_name": "...", "item_amount": 數字, "item_class": "飲食"}
  ]
}
"""

        payload = {
    "model": target_model,  # ✅ 3. 這裡改成剛剛抓到的 target_model
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
            return {
                "store": "辨識失敗",
                "add_amount": 0,
                "add_class": "飲食",
                "add_note": f"錯誤: {str(e)[:50]}",
                "items": []
            }

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
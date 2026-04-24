# web_app/services/invoice_service.py
import os
import re
import base64
from io import BytesIO
from PIL import Image, ImageOps
from sqlalchemy.orm import Session

from ..schemas.invoice import TaiwanUniformInvoice
from .gemini_service import GeminiService

from dotenv import load_dotenv

# 強制重新讀取 .env 檔案
load_dotenv(override=True) 

# 測試看看是否讀到正確的 Key (啟動時會印在終端機)
api_key_check = os.getenv('GEMINI_API_KEY')
# if api_key_check:
#     print(f"DEBUG: 目前使用的 Key 前五碼是 {api_key_check[:5]}")
# else:
#     print("DEBUG: 警告！完全沒讀到 GEMINI_API_KEY，請檢查 .env 檔案內容與位置")
    
class AIAnalysisError(Exception):
    """AI 辨識失敗時拋出，附帶原始回覆供 debug"""
    def __init__(self, message: str, raw_reply: str):
        self.message = message
        self.raw_reply = raw_reply
        super().__init__(self.message)


class InvoiceService:

    # ── 私有方法：從檔案路徑前處理圖片 ──────────────────
    @staticmethod
    def _preprocess_image(image_path: str) -> str:
        """
        從暫存檔案路徑開圖、修正 EXIF 旋轉、壓縮，
        回傳 base64 字串
        """
        with Image.open(image_path) as img:
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGB")
            img.thumbnail((1600, 1600))
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return base64.standard_b64encode(buf.getvalue()).decode()

    # ── 私有方法：從記憶體 bytes 前處理圖片 ─────────────
    @staticmethod
    def _preprocess_image_from_bytes(raw_bytes: bytes) -> str:
        """
        直接從記憶體處理圖片，不需要先存成檔案
        （給 identify_product 用）
        """
        with Image.open(BytesIO(raw_bytes)) as img:
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGB")
            img.thumbnail((1600, 1600))
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return base64.standard_b64encode(buf.getvalue()).decode()

    # ── 私有方法：呼叫 Gemini Vision ─────────────────────
    @staticmethod
    async def _call_gemini(image_b64: str) -> str:
        """
        把 base64 圖片送給 Gemini Vision 辨識發票
        """
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise AIAnalysisError("缺少 GEMINI_API_KEY 環境變數", "")

        system_prompt = """你是台灣發票與收據辨識專家，能辨識所有種類的台灣發票。

    請分析圖片並只回傳以下 JSON，不加任何說明或 markdown：
    {
    "invoice_number": "兩位大寫字母-8位數字，例如 AB-12345678",
    "invoice_period": "例如 114年03-04月",
    "invoice_date": "YYYY-MM-DD",
    "total_amount": 數字,
    "seller_name": "店家或公司名稱，找不到填 null",
    "seller_ban": "8位數字，找不到填 null",
    "buyer_ban": "8位數字，找不到填 null",
    "receipt_type": "電子發票 或 二聯式發票 或 三聯式發票 或 收銀機收據 或 手寫收據",
    "items": [
        {
        "name": "商品名稱",
        "quantity": 數量或null,
        "unit_price": 單價或null,
        "subtotal": 小計或null
        }
    ]
    }

    重要規則：
    - 電子發票通常沒有商品明細，items 填 null 或空陣列
    - 二聯式/三聯式發票若有印商品名稱，請完整列出每一項
    - 收銀機收據通常有完整品項，請仔細辨識每一行
    - 金額欄位只填數字，不要加「元」或「$」"""

        result = await GeminiService.vision_async(
            api_key=api_key,
            model_id="gemini-2.5-flash",
            image_b64=image_b64,
            prompt="請辨識這張台灣發票。",
            system_instruction=system_prompt,
        )

        return str(result.get("text", ""))

    # ── 公開方法：發票辨識主流程 ─────────────────────────
    @staticmethod
    async def extract_invoice_data(
        db: Session,
        user_id: int,
        image_path: str,
    ) -> TaiwanUniformInvoice:
        """
        路由呼叫的入口。
        1. 前處理圖片
        2. 送 Gemini Vision 辨識
        3. 解析 JSON → Pydantic 驗證
        """
        # 1. 圖片前處理
        try:
            image_b64 = InvoiceService._preprocess_image(image_path)
        except Exception as e:
            raise AIAnalysisError(f"圖片前處理失敗：{e}", "")

        # 2. 呼叫 Gemini
        ai_reply = await InvoiceService._call_gemini(image_b64)

        # 3. 擷取 JSON（防禦 Gemini 夾帶 markdown 的情況）
        cleaned = (
            ai_reply.strip()
            .removeprefix("```json")
            .removeprefix("```")
            .removesuffix("```")
            .strip()
        )
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if not match:
            raise AIAnalysisError("Gemini 未回傳有效 JSON", ai_reply)

        json_str = match.group(0)

        # 4. Pydantic 驗證
        try:
            return TaiwanUniformInvoice.model_validate_json(json_str)
        except Exception as e:
            raise AIAnalysisError(f"資料格式驗證失敗：{e}", json_str)

#     # ── 公開方法：商品辨識 ───────────────────────────────
#     @staticmethod
#     async def identify_product(image_b64: str) -> dict:
#         """
#         辨識商品照片，回傳名稱、分類、推估價格
#         """
#         import json

#         api_key = os.getenv("GEMINI_API_KEY") 
#         if not api_key:
#             raise AIAnalysisError("缺少 GEMINI_API_KEY 環境變數", "")

#         system_prompt = """你是一個商品辨識專家，專門辨識台灣市面上的商品。
# 請分析圖片並只回傳以下 JSON，不加任何說明或 markdown：
# {
#     "product_name": "商品完整名稱",
#     "brand": "品牌名稱或 null",
#     "category": "食品/飲料/日用品/3C/服飾/其他",
#     "estimated_price_min": 最低估價數字或null,
#     "estimated_price_max": 最高估價數字或null,
#     "unit": "個/瓶/包/件 等單位",
#     "description": "30字以內的商品簡述"
# }"""

#         user_prompt = f"data:image/jpeg;base64,{image_b64}\n\n請辨識這個商品。"

#         result = await GeminiService.chat_async(
#             api_key=api_key,
#             model_id="gemini-1.5-flash",
#             prompt=user_prompt,
#             system_instruction=system_prompt,
#         )

#         ai_reply = str(result.get("text", ""))
#         cleaned = (
#             ai_reply.strip()
#             .removeprefix("```json")
#             .removeprefix("```")
#             .removesuffix("```")
#             .strip()
#         )
#         match = re.search(r'\{.*\}', cleaned, re.DOTALL)
#         if not match:
#             raise AIAnalysisError("Gemini 未回傳有效 JSON", ai_reply)

#         return json.loads(match.group(0))
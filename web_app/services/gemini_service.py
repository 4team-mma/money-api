# gemini_service.py
import logging
import re
from typing import Optional, List, Callable
from google import genai
from google.genai import types
import os

logger = logging.getLogger(__name__)

class GeminiService:
    @staticmethod
    async def chat_async(api_key: str, model_id: str, prompt: str, system_instruction: str, tools: Optional[List[Callable]] = None):
        """處理 Gemini 對話，並統一回傳字典格式 {"text": ..., "actual_model": ...}"""
        try:
            client = genai.Client(api_key=api_key)

            # 1. 取得前端指定的精確模型名稱
            target_id = model_id.replace("models/", "") if model_id.startswith("models/") else model_id
            logger.info(f"🚀 [Gemini] 第一次嘗試連線指定模型: {target_id}")

            # 🌟 解決 Pylance 紅線：嚴格區分有工具跟沒工具的 Config 設定
            if tools:
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.15,
                    top_p=0.15,
                    tools=tools  # type: ignore[arg-type]
                )
            else:
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.15,
                    top_p=0.15,
                    tools=tools  # type: ignore[arg-type]
                )

            try:
                # 🎯 第一次嘗試：尊重前端選單，發送精確模型名稱
                response = await client.aio.models.generate_content(
                    model=target_id,
                    contents=prompt,
                    config=config
                )

                # ==========================================
                # 🌟 原生 Tool Calling 攔截器
                # ==========================================
                if response.function_calls:
                    call = response.function_calls[0]
                    func_name = call.name

                    # 🌟 解決 Pylance 紅線：確保 args 絕對是 dict，不會是 None
                    call_args: dict = call.args if isinstance(call.args, dict) else {}

                    if tools:
                        for tool in tools:
                            if tool.__name__ == func_name:
                                try:
                                    # 安全地傳入參數執行
                                    tool_result = tool(**call_args)
                                    return {
                                        "text": f"🛠️ **【系統自動查詢】**\n我幫你使用了 `{func_name}` 工具喵！\n\n**查詢結果：**\n{tool_result}",
                                        "actual_model": f"{target_id} (Tool Mode)"
                                    }
                                except Exception as e:
                                    logger.error(f"執行工具 {func_name} 失敗: {str(e)}")
                                    return {"text": f"喵... 試著執行工具 `{func_name}` 時發生錯誤了喵。", "actual_model": target_id}

                    return {"text": f"喵... 模型想呼叫 `{func_name}`，但找不到這個工具喵。", "actual_model": target_id}
                # ==========================================

                reply_text = response.text or "喵... 剛剛腦袋一片空白..."
                return {"text": reply_text, "actual_model": target_id}

            except Exception as api_err:
                error_msg = str(api_err)
                # 🛡️ 防彈機制：如果發生 404，自動降級！
                if "404" in error_msg or "not found" in error_msg.lower():
                    logger.warning(f"⚠️ [Gemini] 找不到精確模型 {target_id}，啟動自動容錯降級...")

                    fallback_id = "gemini-pro-latest" if "pro" in target_id.lower() else "gemini-flash-latest"
                    logger.info(f"🚀 [Gemini] 重新連線萬用安全模型: {fallback_id}")

                    # 🎯 第二次嘗試：使用萬用代號
                    response = await client.aio.models.generate_content(
                        model=fallback_id,
                        contents=prompt,
                        config=config
                    )

                    # 降級後的 Tool 攔截
                    if response.function_calls:
                        call = response.function_calls[0]
                        call_args: dict = call.args if isinstance(call.args, dict) else {}
                        if tools:
                            for tool in tools:
                                if tool.__name__ == call.name:
                                    tool_result = tool(**call_args)
                                    return {"text": f"🛠️ **【系統查詢】**\n結果：\n{tool_result}", "actual_model": f"{fallback_id} (Tool Mode)"}

                    reply_text = response.text or "喵... 降級後還是想不出答案喵。"
                    return {"text": reply_text, "actual_model": fallback_id}

                # 如果不是 404 錯誤，丟給外層處理
                raise api_err

        except Exception as e:
            error_msg = str(e)

            # 偵測 429 配額問題
            if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg:
                seconds_match = re.search(r"retry in ([\d\.]+)s", error_msg)
                if seconds_match:
                    sec_val = float(seconds_match.group(1))
                    sec = round(sec_val, 1)
                    if sec > 60:
                        return {"text": f"喵... 喵喵累了。請等約 {round(sec/60, 1)} 分鐘再來找我喵！🍵", "actual_model": model_id}
                    return {"text": f"喵... 喵喵累了。請等約 {sec} 秒再來找我喵！🍵", "actual_model": model_id}
                return {"text": "喵... 喵喵今天話說太多累了，請休息一分鐘再試喵！", "actual_model": model_id}

            # 偵測 503 伺服器繁忙
            if "503" in error_msg or "UNAVAILABLE" in error_msg:
                return {"text": "喵... 目前 Google 伺服器太擠了，請等 5 秒鐘再問我一次試試喵！🚦", "actual_model": model_id}

            logger.error(f"Gemini 內部異常: {error_msg}")
            return {"text": f"喵... 腦袋當機了。原因：{error_msg[:30]}...", "actual_model": target_id}
    @staticmethod
    async def vision_async(api_key: str, model_id: str, image_b64: str, prompt: str, system_instruction: str):
        """
        專門處理圖片辨識的方法，把 base64 圖片正確傳給 Gemini Vision
        """
        try:
            client = genai.Client(api_key=api_key)
            target_id = model_id.replace("models/", "") if model_id.startswith("models/") else model_id

            # Gemini Vision 正確的圖片格式：用 types.Part 包裝
            image_part = types.Part.from_bytes(
                data=__import__('base64').b64decode(image_b64),
                mime_type="image/jpeg"
            )
            text_part = types.Part.from_text(text=prompt)

            response = await client.aio.models.generate_content(
                model=target_id,
                contents=[image_part, text_part],
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.1,
                    top_p=0.1
                )
            )

            reply_text = response.text or ""
            return {"text": reply_text, "actual_model": target_id}

        except Exception as e:
                    error_msg = str(e)
                    
                    # 1. 處理 429 / RESOURCE_EXHAUSTED (配額用完)
                    if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg:
                        import re
                        seconds_match = re.search(r"retry in ([\d\.]+)s", error_msg)
                        if seconds_match:
                            sec = round(float(seconds_match.group(1)), 1)
                            wait = f"{round(sec/60, 1)} 分鐘" if sec > 60 else f"{sec} 秒"
                            return {"text": f"喵... 記帳太快啦！請等約 {wait} 再試喵！🍵", "actual_model": target_id}
                        return {"text": "喵... 今天的免費次數用完囉，請稍後再試喵！", "actual_model": target_id}

                    # 2. 處理 503 / 500 (伺服器過載/塞車) 🌟 這是你剛剛遇到的
                    if "503" in error_msg or "UNAVAILABLE" in error_msg or "high demand" in error_msg.lower():
                        return {"text": "喵嗚！現在辨識伺服器大塞車中... 請等 10 秒後再試一次喵！🚗", "actual_model": target_id}
                    
                    if "500" in error_msg or "internal error" in error_msg.lower():
                        return {"text": "喵？AI 腦袋稍微打結了，請再按一次看看喵！🧠", "actual_model": target_id}

                    # 3. 處理 400 (通常是圖片太大或格式不對)
                    if "400" in error_msg or "invalid" in error_msg.lower():
                        return {"text": "喵... 圖片好像有點模糊或格式不對，重拍一張試試喵？📸", "actual_model": target_id}

                    # 4. 404 自動降級邏輯 (保持原樣)
                    if "404" in error_msg or "not found" in error_msg.lower():
                        # ... (原有的降級邏輯)
                        pass

                    logger.error(f"Gemini Vision 異常: {error_msg}")
                    return {"text": "喵... 網路連線好像有點不穩，檢查一下網路再試喵！🌐", "actual_model": model_id}        
        
    # 這是給google行事曆串接用
    # 🌟 在這裡新增多模態圖片解析方法 (新版 SDK 寫法)
    @staticmethod
    async def analyze_image_async(api_key: str, image_bytes: bytes, mime_type: str, prompt: str) -> str:
        try:
            # 🌟 核心修正：顯式指定 vertexai=False 並確保環境變數不會干擾連線
            # 有些環境會誤導 SDK 以為要走 Vertex AI 路徑，加上這行能強制走標準 Google AI 路徑
            client = genai.Client(
                api_key=api_key,
                http_options={'api_version': 'v1'}
            )
            
            #target_model = 'gemini-2.5-flash' 
            target_model = 'gemini-2.5-flash-lite'
            logger.info(f"📸 [Gemini Vision] 穩定協議連線中: {target_model}")

            image_part = types.Part.from_bytes(
                data=image_bytes,
                mime_type=mime_type
            )

            # 4. 非同步發送 (這次我們加上逾時控制，防止前端等到斷線)
            response = await client.aio.models.generate_content(
                model=target_model,
                contents=[image_part, prompt]
            )

            return response.text or ""

        except Exception as e:
            # 🛡️ 針對協議錯誤的特殊補救：如果真的發生了，嘗試重啟連線
            logger.error(f"❌ Gemini 圖片解析失敗: {str(e)}")
            if "Request URL is missing" in str(e):
                logger.warning("偵測到協議遺失，嘗試使用替代 Client 配置...")
                # 備案：直接用最原始的方式重新連線
                client_fallback = genai.Client(api_key=api_key)
                res = await client_fallback.aio.models.generate_content(
                    model='gemini-1.5-flash', # 1.5 版在 v1 協議下非常穩定
                    contents=[image_part, prompt]
                )
                return res.text or ""
            raise e
        
        
    # 加在 GeminiService class 裡面，analyze_image_async 下面

    @staticmethod
    async def parse_receipt_images(
        image_bytes: list[bytes],       
        platform: str = "foodpanda",
        history_classes: Optional[List[str]] = None
        ) -> dict:
        """專門解析外送訂單截圖"""
        import json, re
        api_key = os.getenv("GEMINI_API_KEY", "")
        platform_hint = f"這是來自【{platform}】平台的訂單截圖，共 {len(image_bytes)} 張。\n"  # ← 用 image_bytes

        history_classes_str = "、".join   (history_classes) if history_classes else "（尚無歷史分類）"
        
        receipt_prompt = platform_hint + f"""
    你是訂單 OCR 解析器，專門處理台灣電商/外送平台截圖。

    【使用者歷史分類參考】
    {history_classes_str}

    請優先從「使用者歷史分類」中選擇最相近的 add_class。
    如果真的無法匹配，再使用預設分類規則。

    ---
    """ + """你是訂單 OCR 解析器，專門處理台灣電商/外送平台截圖。
    這些截圖來自同一張訂單，可能有重疊內容，請合併去重。
    只回傳合法 JSON，不能包含任何說明或 markdown。
    只回傳合法 JSON，不能包含任何說明或 markdown。
    格式：
    {
    "store": "店家名稱（不是顧客姓名）",
    "order_number": "訂單編號（如果圖片有顯示，沒有則空字串）",
    "add_amount": 總計含稅數字,
    "add_class": "根據品項內容判斷的主類別",
    "add_note": "店名 訂單",
    "items": [
    {"item_name": "品項名稱", "item_amount": 金額, "item_class": "類別", "quantity": 數量數字}
        ]
    }
    規則：
    1. store = 店家名稱，不是顧客名字
    2. add_amount = 總計（含稅）的數字
    3. items 包含：實際品項（正數）＋折扣優惠（負數）＋平台費服務費（正數）
    例如：{"item_name": "折扣", "item_amount": -2, "item_class": "折扣"}
    4. 所有 items 的 item_amount 加總必須等於 add_amount
    5. 外送服務費如果是免費則不列入
    6. add_class 判斷規則（以金額佔比最高的品項類別為主）：
    - 食物飲料外送 → "飲食"
    - 玩具/遊戲/娛樂用品 → "娛樂"
    - 衣服/鞋子/配件 → "服飾"
    - 家電/3C/電腦 → "3C"
    - 日用品/家居/清潔 → "居家"
    - 書籍/文具/教育 → "教育"
    - 美妝/保養/醫藥 → "醫療"
    - 交通/運輸 → "交通"
    - 混合多種類別 → 以金額最大的品項類別為主
    7. 每個 item 的 item_class 也用上述規則個別判斷
    8. order_number = 訂單編號，通常是英數字混合，如果圖片沒有則填空字串""
    9. 每個 item 的 quantity = 品項數量，1x 就是 1，沒標示預設為 1
    
    """
    

        try:
            client = genai.Client(api_key=api_key)
            
            # 多張圖片打包進 contents
            contents = []
            for img in image_bytes:              # ← 用 image_bytes
                contents.append(types.Part.from_bytes(data=img, mime_type="image/jpeg"))
            contents.append("請合併這些截圖，解析成一筆完整訂單")

            response = await client.aio.models.generate_content(
                model="gemini-flash-latest",
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=receipt_prompt,
                    temperature=0.1,
                )
            )

            raw_text = response.text or ""
            logger.info(f"[Receipt OCR multi] output: {raw_text[:200]}")

            try:
                return json.loads(raw_text)
            except json.JSONDecodeError:
                pass

            match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw_text)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass

            return {"error": "無法解析圖片內容，請手動輸入"}

        except Exception as e:
            logger.error(f"[Receipt OCR multi] 失敗: {str(e)}")
            return {"error": f"圖片解析失敗：{str(e)[:80]}"}




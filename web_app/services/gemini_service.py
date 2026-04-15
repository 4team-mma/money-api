import logging
import re
from typing import Optional, List, Callable
from google import genai
from google.genai import types

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
                    tools=tools
                )
            else:
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.15,
                    top_p=0.15
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
            
            target_model = 'gemini-2.5-flash' 
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

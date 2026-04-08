import logging
import re
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

class GeminiService:
    @staticmethod
    async def chat_async(api_key: str, model_id: str, prompt: str, system_instruction: str):
        """處理 Gemini 對話，並統一回傳字典格式 {"text": ..., "actual_model": ...}"""
        try:
            client = genai.Client(api_key=api_key)
            
            # 1. 取得前端指定的精確模型名稱
            target_id = model_id.replace("models/", "") if model_id.startswith("models/") else model_id
            logger.info(f"🚀 [Gemini] 第一次嘗試連線指定模型: {target_id}")

            try:
                # 🎯 第一次嘗試：尊重前端選單，發送精確模型名稱
                response = await client.aio.models.generate_content(
                    model=target_id, 
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.15,
                        top_p=0.15
                    )
                )
                reply_text = response.text or "喵... 剛剛腦袋一片空白..."
                # 🚀 成功連線，回傳真實模型名稱
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
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.15,
                            top_p=0.15
                        )
                    )
                    
                    
                    # 🚀 關鍵修改：直接回傳乾淨的答案，不要再接「喵小提醒」了！
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
                        return {"text": f"喵... 喵喵累了。請等約 {round(sec/60, 1)} 分鐘再來找我喵！🍵", "actual_model": target_id}
                    return {"text": f"喵... 喵喵累了。請等約 {sec} 秒再來找我喵！🍵", "actual_model": target_id}
                return {"text": "喵... 喵喵今天話說太多累了，請休息一分鐘再試喵！", "actual_model": target_id}
            
            # 偵測 503 伺服器繁忙
            if "503" in error_msg or "UNAVAILABLE" in error_msg:
                return {"text": "喵... 目前 Google 伺服器太擠了，請等 5 秒鐘再問我一次試試喵！🚦", "actual_model": target_id}

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
            if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg:
                import re
                seconds_match = re.search(r"retry in ([\d\.]+)s", error_msg)
                if seconds_match:
                    sec = round(float(seconds_match.group(1)), 1)
                    wait = f"{round(sec/60, 1)} 分鐘" if sec > 60 else f"{sec} 秒"
                    return {"text": f"喵... 額度用完了，請等約 {wait} 再試喵！🍵", "actual_model": target_id}
                return {"text": "喵... API 配額超限，請稍後再試喵！", "actual_model": target_id}
            # 404 自動降級到 flash
            if "404" in error_msg or "not found" in error_msg.lower():
                fallback_id = "gemini-2.5-flash"
                client = genai.Client(api_key=api_key)
                image_part = types.Part.from_bytes(
                    data=__import__('base64').b64decode(image_b64),
                    mime_type="image/jpeg"
                )
                response = await client.aio.models.generate_content(
                    model=fallback_id,
                    contents=[image_part, types.Part.from_text(text=prompt)],
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.1,
                    )
                )
                return {"text": response.text or "", "actual_model": fallback_id}

            logger.error(f"Gemini Vision 異常: {error_msg}")
            raise Exception(f"Gemini Vision 呼叫失敗：{error_msg}")
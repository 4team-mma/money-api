import logging
import re
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

class GeminiService:
    @staticmethod
    async def chat_async(api_key: str, model_id: str, prompt: str, system_instruction: str):
        """處理 Gemini 對話，並修正參數位置與錯誤美化"""
        try:
            client = genai.Client(api_key=api_key)
            
            # 自動修正模型名稱別名，確保連線穩定
            if "flash" in model_id.lower():
                target_id = "gemini-flash-latest"
            elif "pro" in model_id.lower():
                target_id = "gemini-pro-latest"
            else:
                target_id = model_id.replace("models/", "")
            
            # 🚀 正確的參數結構：temperature 必須在 config 裡面
            response = await client.aio.models.generate_content(
                model=target_id, 
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.15,  # 🚀 強制設定為 0.1，這會讓它完全聽從 Prompt 不敢亂噴
                    top_p=0.15
                            )
            )
            return response.text

        except Exception as e:
            error_msg = str(e)
            # 偵測 429 配額問題
            if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg:
                seconds_match = re.search(r"retry in ([\d\.]+)s", error_msg)
                if seconds_match:
                    sec_val = float(seconds_match.group(1))
                    sec = round(sec_val, 1)
                    if sec > 60:
                        return f"喵... 喵喵累了。請等約 {round(sec/60, 1)} 分鐘再來找我喵！🍵"
                    return f"喵... 喵喵累了。請等約 {sec} 秒再來找我喵！🍵"
                return "喵... 喵喵今天話說太多累了，請休息一分鐘再試喵！"
            
            # 偵測 503 伺服器繁忙
            if "503" in error_msg or "UNAVAILABLE" in error_msg:
                return "喵... 目前 Google 伺服器太擠了，請等 5 秒鐘再問我一次試試喵！🚦"

            logger.error(f"Gemini 內部異常: {error_msg}")
            return f"喵... 腦袋當機了。原因：{error_msg[:30]}..."
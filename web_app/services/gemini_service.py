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
            return {"text": f"喵... 腦袋當機了。原因：{error_msg[:30]}...", "actual_model": model_id}
# web_app/services/ollama_service.py
import httpx
import logging
import inspect  
from typing import Optional

logger = logging.getLogger(__name__)

class OllamaService:
    
    @staticmethod
    def _function_to_tool(func):
        """🌟 打工仔函數：將 Python 函數轉換為 Ollama 看得懂的 JSON 格式"""
        sig = inspect.signature(func)
        props = {}
        required = []
        
        for name, param in sig.parameters.items():
            ptype = "string"
            if param.annotation == int: ptype = "integer"
            elif param.annotation == float: ptype = "number"
            elif param.annotation == bool: ptype = "boolean"
            
            props[name] = {
                "type": ptype,
                "description": param.annotation.__name__ if param.annotation != inspect._empty else "參數"
            }
            if param.default == inspect.Parameter.empty:
                required.append(name)

        func_name = getattr(func, "name", func.__name__)
        func_desc = getattr(func, "description", func.__doc__ or "執行特定功能")

        return {
            "type": "function",
            "function": {
                "name": func_name,
                "description": func_desc,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": required
                }
            }
        }

    @staticmethod
    async def chat_async(base_url: str, model_id: str, prompt: str, system_instruction: str, timeout_sec: float = 60.0, tools: Optional[list] = None):
        """處理 Ollama 本地模型對話 (支援自動切換 Tool-Capable 模型)"""
        try:
            ollama_tools = []
            tool_map = {}  
            if tools:
                for t in tools:
                    if callable(t) or hasattr(t, "name"):
                        schema = OllamaService._function_to_tool(t)
                        ollama_tools.append(schema)
                        func_name = schema["function"]["name"]
                        tool_map[func_name] = t

            messages = [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ]

            payload = {
                # model 稍後會在迴圈中動態指定
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": 0.2,  
                    "num_ctx": 4096      
                }
            }
            
            # ==========================================
            # 🌟 核心：動態決定要嘗試的模型清單
            # ==========================================
            if ollama_tools:
                payload["tools"] = ollama_tools
                # 當需要使用工具時，自動替換成支援 Tool Calling 的模型 (優先 qwen，備胎 llama)
                models_to_try = ["llama3.1:latest", "qwen2.5:latest"]
            else:
                # 純聊天狀態，保持原本後台預設模型 (如 gemma3:4b)
                models_to_try = [model_id]

            async with httpx.AsyncClient() as client:
                res = None
                
                
                # 🔄 開始嘗試連線，如果失敗就換下一個模型
                for target_model in models_to_try:
                    payload["model"] = target_model
                    logger.info(f"Ollama Request: {base_url} | Model: {target_model} | Tools count: {len(ollama_tools)}")

                    res = await client.post(
                        f"{base_url}/api/chat",
                        json=payload,
                        timeout=httpx.Timeout(timeout_sec, connect=5.0)
                    )

                    if res.status_code == 200:
                        
                        break # 連線成功，跳出迴圈
                    else:
                        logger.warning(f"Ollama Error 嘗試 {target_model} 失敗 (Status: {res.status_code}): {res.text}")
                        # 發生 400 (不支援工具) 或 404 (沒安裝模型) 等錯誤，繼續嘗試下一個
                        continue

                # 如果備胎清單都試完了還是失敗
                if not res or res.status_code != 200:
                    return f"喵... 地端模型連線失敗 (嘗試了 {models_to_try} 喵，請確認 Ollama 有下載對應模型！)"

                data = res.json()
                response_msg = data.get("message", {})

                # ==========================================
                # 處理工具呼叫的邏輯 (這段只有成功連線才會執行)
                # ==========================================
                if "tool_calls" in response_msg and response_msg["tool_calls"]:
                    messages.append(response_msg)
                    
                    for tc in response_msg["tool_calls"]:
                        func_name = tc["function"]["name"]
                        func_args = tc["function"]["arguments"]
                        
                        logger.info(f"🔧 [Ollama Tool Call] 觸發工具: {func_name} | 參數: {func_args}")
                        
                        if func_name in tool_map:
                            func = tool_map[func_name]
                            try:
                                if inspect.iscoroutinefunction(func):
                                    result = await func(**func_args)
                                else:
                                    result = func(**func_args)
                            except Exception as e:
                                logger.error(f"工具 {func_name} 執行失敗: {e}", exc_info=True)
                                result = f"執行失敗: {str(e)}"
                            
                            messages.append({
                                "role": "tool",
                                "content": str(result)
                            })
                    
                    # 再次發送請求，讓模型根據工具執行的結果給出最終回覆
                    payload["messages"] = messages
                    payload.pop("tools", None) 
                    # 此時 payload["model"] 已經是迴圈中成功的 used_model，不用重新設定
                    
                    final_res = await client.post(
                        f"{base_url}/api/chat",
                        json=payload,
                        timeout=httpx.Timeout(timeout_sec, connect=5.0)
                    )
                    
                    if final_res.status_code == 200:
                        return final_res.json()["message"]["content"]
                    else:
                        return f"喵... 工具執行完但整理結果失敗 ({final_res.status_code})"

# ==========================================
                # 🛡️ Fallback: 偵測模型把 tool call 當文字吐出的情況
                # ==========================================
                raw_content = response_msg.get("content", "")
                if raw_content and tool_map:
                    import re, json as _json
                    # qwen2.5 常見的兩種純文字格式：
                    # 1. {"name": "fn", "arguments": {...}}
                    # 2. <tool_call>{"name": "fn", "arguments": {...}}</tool_call>

                    
                    # 先嘗試 <tool_call> 標籤格式
                    tag_match = re.search(r'<tool_call>\s*(\{.*?\})\s*</tool_call>', raw_content, re.DOTALL)
                    plain_match = re.search(r'(\{["\']name["\']\s*:\s*["\'][^"\']+["\'].*?\})', raw_content, re.DOTALL)
                    
                    parsed_call = None
                    for m in [tag_match, plain_match]:
                        if m:
                            try:
                                candidate = _json.loads(m.group(1))
                                if "name" in candidate and ("arguments" in candidate or "parameters" in candidate):
                                    parsed_call = candidate
                                    break
                            except (_json.JSONDecodeError, Exception):
                                continue
                    
                    if parsed_call:
                        func_name = parsed_call.get("name", "")
                        # qwen2.5 有時用 "arguments"，有時用 "parameters"
                        func_args = parsed_call.get("arguments") or parsed_call.get("parameters") or {}
                        
                        logger.info(f"🛡️ [Ollama Fallback] 純文字 tool call 攔截成功: {func_name} | 參數: {func_args}")
                        
                        if func_name in tool_map:
                            func = tool_map[func_name]
                            try:
                                if inspect.iscoroutinefunction(func):
                                    result = await func(**func_args)
                                else:
                                    result = func(**func_args)
                            except Exception as e:
                                logger.error(f"Fallback 工具 {func_name} 執行失敗: {e}", exc_info=True)
                                result = f"執行失敗: {str(e)}"
                            
                            # 把結果組回去讓模型整理成自然語言
                            messages.append(response_msg)
                            messages.append({"role": "tool", "content": str(result)})
                            payload["messages"] = messages
                            payload.pop("tools", None)
                            
                            final_res = await client.post(
                                f"{base_url}/api/chat",
                                json=payload,
                                timeout=httpx.Timeout(timeout_sec, connect=5.0)
                            )
                            if final_res.status_code == 200:
                                return final_res.json()["message"]["content"]
                            else:
                                return str(result)  # 至少把原始結果吐出來
                # ==========================================



                # 一般聊天回覆
                return response_msg.get("content", "喵喵不知道怎麼回答...")

        except Exception as e:
            logger.error(f"Ollama Connection Error: {str(e)}")
            return f"喵... 呼叫地端模型失敗，請確認 Ollama 有開喵: {str(e)[:50]}"

    @staticmethod
    async def chat_stream_async(base_url: str, model_id: str, prompt: str, system_instruction: str):
        from langchain_community.llms import Ollama
        llm = Ollama(base_url=base_url, model=model_id, system=system_instruction)
        async for chunk in llm.astream(prompt):
            yield chunk
# routers/admin_ai_helper.py
from fastapi import APIRouter, Body
from pydantic import BaseModel
from ..services.ollama_service import OllamaService

router = APIRouter(prefix="/api/admin/dev-assist", tags=["Admin AI Helper"])

class DevRequest(BaseModel):
    mode: str  # 'test_script', 'bug_fix', 'sql_gen'
    context: str

@router.post("/generate")
async def generate_code(request: DevRequest):
    # 1. 根據不同模式，指派不同的 System Prompt
    system_prompts = {
        "test_script": "你是一個資深 Python 測試工程師。請根據使用者的需求，只輸出純 Python 測試腳本程式碼（如 Locust 或 pytest），不要包含任何解釋或 markdown 標記以外的廢話。",
        "bug_fix": "你是一個 FastAPI 與 Vue 的除錯專家。請分析使用者提供的程式碼或錯誤日誌，並給出修正後的完整程式碼與簡短的錯誤原因說明。"
    }
    
    instruction = system_prompts.get(request.mode, "你是一個專業程式開發助手。")
    
    # 2. 呼叫你現有的 OllamaService (這段跟你之前做資安 log 分析很像)
    prompt = f"使用者的需求：\n{request.context}"
    
    try:
        # 直接呼叫地端 gemma4:e4b
        generated_code = await OllamaService.chat_async(
            base_url="http://localhost:11434",
            model_id="gemma4:e4b",
            prompt=prompt,
            system_instruction=instruction
        )
        return {"status": "success", "code": generated_code}
    except Exception as e:
        return {"status": "error", "message": str(e)}
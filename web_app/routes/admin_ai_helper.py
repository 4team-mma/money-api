# routers/admin_ai_helper.py
from fastapi import APIRouter, Depends
from ..services.ollama_service import OllamaService
from ..schemas.ai import DevRequest
from ..dependencies import admin_required
from ..models import Member
#from langchain_chroma import Chroma
from ..services.vector_db_tools import VectorDBTools
import os
router = APIRouter()


# 建立 B1 圖書館管理員
def search_codebase(query: str):
    # 🌟 終極修正：直接向兵器庫索取 B1 的箱子！
    # 這樣它就會自動帶上 nomic-embed-text (768維度) 的正確鑰匙！
    vectorstore = VectorDBTools.get_codebase_store()
    
    # 找出跟使用者問題最相關的 5 塊程式碼
    docs = vectorstore.similarity_search(query, k=5)
    
    # 把找出來的程式碼組合成字串
    context = ""
    for doc in docs:
        source_file = doc.metadata.get('source', '未知檔案')
        context += f"\n\n--- 來自檔案: {source_file} ---\n{doc.page_content}"
    
    return context

@router.post("/generate")
async def generate_code(request: DevRequest, current_admin: Member = Depends(admin_required)):
    
    # 🌟 防呆機制：如果是雲端環境 (Render)，直接拒絕服務！
    is_on_render = os.getenv("RENDER") == "true"
    if is_on_render:
        return {
            "status": "error", 
            "message": "⚠️ 資安限制：雲端環境已禁用此 AI 開發輔助功能。請於 Localhost 地端環境使用喵！"
        }
    
    print(f"👨‍💻 管理員 {current_admin.username} ({current_admin.user_id}) 正在請求 AI 協助...") 
    
    
    # 🌟 階段三：全專案 RAG 查詢 (解鎖 B1)
    if request.mode == "stage3":
        # 1. 檢索程式碼
        retrieved_context = search_codebase(request.context)
        
        # 2. 組合 Prompt
        instruction = "你是一個資深的系統架構師與全端工程師。請閱讀以下我提供的【專案現有程式碼】，並根據使用者的需求給出精確的修改建議或完整程式碼。"
        prompt = f"【現有專案程式碼參考】:\n{retrieved_context}\n\n【使用者的問題】:\n{request.context},"
        
    else:
        # 階段一 & 階段二 原本的邏輯
        system_prompts = {
            "test_script": "你是一個資深 Python 測試工程師。請根據需求，只輸出純 Python 測試腳本程式碼，不要廢話。",
            "bug_fix": """你是一個 FastAPI 與 Vue 的除錯專家。
            【公司最高開發準則】：
            1. 實作 API 速率限制 (Rate Limit) 時，絕對只能使用 `slowapi`，嚴禁使用 `fastapi-limiter`。
            2. 請分析使用者提供的程式碼，給出修正後的完整程式碼與說明。"""
        }
        instruction = system_prompts.get(request.mode, "你是一個專業程式開發助手。")
        prompt = f"使用者的需求：\n{request.context}"
    
    try:
        # 呼叫地端 gemma4:e4b
        generated_code = await OllamaService.chat_async(
            base_url="http://localhost:11434",
            model_id="gemma4:e4b",
            prompt=prompt,
            system_instruction=instruction
        )
        return {"status": "success", "code": generated_code}
    except Exception as e:
        return {"status": "error", "message": str(e)}
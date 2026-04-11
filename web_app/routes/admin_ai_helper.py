# routers/admin_ai_helper.py
from fastapi import APIRouter, Depends
from ..services.ollama_service import OllamaService
from ..schemas.ai import DevRequest
from ..dependencies import admin_required
from ..models import Member
#from langchain_chroma import Chroma
from ..services.vector_db_tools import VectorDBTools
import os
from fastapi.responses import StreamingResponse

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
    
    is_on_render = os.getenv("RENDER") == "true"
    if is_on_render:
        return {"status": "error", "message": "⚠️ 資安限制：雲端環境已禁用此功能。"}
    
    print(f"👨‍💻 管理員 {current_admin.username} ({current_admin.user_id}) 正在請求 AI 協助...") 
    
    # 🌟 新增：v0 風格的結構化輸出規則
    THINK_RULE = """
    \n【回覆格式規定】：
    請務必嚴格遵循以下格式輸出你的回答，不要省略任何步驟：
    ### 🔍 1. 問題拆解與分析
    (請用 2~3 行精簡說明你發現了什麼問題)

    ### 💡 2. 解決方案與推理
    (說明你打算怎麼改，以及為什麼這樣改)

    ### 💻 3. 完整程式碼實作
    (輸出修正後的程式碼)
    """
    
    if request.mode == "stage3":
        retrieved_context = search_codebase(request.context)
        # 🌟 將規則加在 instruction 的尾巴
        instruction = "你是一個資深的系統架構師與全端工程師。請閱讀以下我提供的【專案現有程式碼】，並根據使用者的需求給出精確的修改建議或完整程式碼。" + THINK_RULE
        prompt = f"【現有專案程式碼參考】:\n{retrieved_context}\n\n【使用者的問題】:\n{request.context}"
    else:
        system_prompts = {
            # 🌟 將規則加在各個模式的尾巴
            "test_script": """你是一個資深 Python 測試工程師。請根據需求，只輸出純 Python 測試腳本程式碼，不要廢話。
            【強制測試開發規範】：
            當撰寫非同步 (async) API 測試時，絕對禁止假設全域有 `client` fixture 可以用。
            須在測試函式內部，明確使用 `async with httpx.AsyncClient() as client:` 來建立連線！""" + THINK_RULE,
            
            "bug_fix": f"你是一個 FastAPI 與 Vue 的除錯專家。\n【公司最高開發準則】：\n1. 實作 API 速率限制 (Rate Limit) 時，絕對只能使用 `slowapi`。\n2. 請分析使用者提供的程式碼，給出修正後的完整程式碼。{THINK_RULE}"
        }
        instruction = system_prompts.get(request.mode, "你是一個專業程式開發助手。" + THINK_RULE)
        prompt = f"使用者的需求：\n{request.context}"
    
    # 🌟 建立純文字產生器：一個字一個字往前端送
    async def stream_generator():
        try:
            # 確保你的 OllamaService.py 裡面有 chat_stream_async 方法！
            async for chunk in OllamaService.chat_stream_async(
                base_url="http://localhost:11434",
                model_id="gemma4:e4b",
                prompt=prompt,
                system_instruction=instruction
            ):
                yield chunk
        except Exception as e:
            yield f"\n\n[系統錯誤]: {str(e)}"

    return StreamingResponse(stream_generator(), media_type="text/plain")
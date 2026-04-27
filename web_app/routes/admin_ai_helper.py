# routers/admin_ai_helper.py
from fastapi import APIRouter, Depends, HTTPException
from ..services.ollama_service import OllamaService
from ..schemas.ai import DevRequest
from ..schemas.admin_ragB1test import RagTestRequest, RagLogCreate
from ..dependencies import admin_required, get_current_user
from ..models import Member,RagPerformanceLog
#from langchain_chroma import Chroma
from ..services.vector_db_tools import VectorDBTools
from ..services.admin_lab_service import AdminLabService # 引用~
import os
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session # 🌟 解決 Undefined name `Session`
from ..database import get_db # 🌟 解決 Undefined name `get_db`


router = APIRouter()


# 🌟 2. 建立專屬於 B1 沙盒的權限檢查機制
async def lab_tester_required(current_user: Member = Depends(get_current_user)):
    
    print("="*40)
    print(f"🚨 [後門權限檢查] 嘗試進入 B1 實驗室...")
    print(f"👉 登入帳號 (username): '{current_user.username}'")
    print(f"👉 帳號權限 (role): '{current_user.role}'")
    
    # 🎯 破案修正：檢查 role 欄位是不是 'admin' 或 'ai_test'
    if current_user.role in ['admin', 'ai_test']: 
        print("🟢 檢查通過：允許放行！")
        print("="*40)
        return current_user
    
    print("🔴 檢查失敗：條件不符，擋在門外！")
    print("="*40)
    raise HTTPException(status_code=403, detail="權限不足，僅限管理員或 B1 測試員存取")


# 建立 B1 圖書館管理員
def search_codebase(query: str):
    
    # 🛡️ 防呆機制：如果輸入超過 1000 字，強行截斷，避免撐爆 Ollama Embedding 模型
    safe_query = query[:1000]
    
    # 這樣它就會自動帶上 nomic-embed-text (768維度) 的正確鑰匙！
    vectorstore = VectorDBTools.get_codebase_store()
    
    # 找出跟使用者問題最相關的 5 塊程式碼
    # 使用截斷後的安全字串去向量庫搜尋
    docs = vectorstore.similarity_search(safe_query, k=5)
    
    # 把找出來的程式碼組合成字串
    context = ""
    for doc in docs:
        source_file = doc.metadata.get('source', '未知檔案')
        context += f"\n\n--- 來自檔案: {source_file} ---\n{doc.page_content}"
    
    return context




@router.post("/generate")
async def generate_code(request: DevRequest, current_admin: Member = Depends(lab_tester_required)):
    
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
            
            "bug_fix": f"你是一個 FastAPI 與 Vue 的除錯專家。\n【公司最高開發準則】：\n1. 實作 API 速率限制 (Rate Limit) 時，絕對只能使用 `slowapi`。\n2. 請分析使用者提供的程式碼，給出修正後的完整程式碼。{THINK_RULE}",
            
            # 🌟 新增：專門用來生成微調資料的特化 Prompt
            "dataset_gen": """你現在是一個無情的 JSONL 資料生成機器。
            【最高強制防呆指令】：
            1. 絕對禁止輸出任何開場白、思考過程或結尾語（例如「好的」、「以下是」）。
            2. 絕對禁止使用 ```json 或 ```jsonl 這樣的 Markdown 標記將內容包起來。
            3. 你的輸出的第一個字元必須是 { ，每一行必須是一個獨立且合法的 JSON 物件。

            """
            }
        
        
        instruction = system_prompts.get(request.mode, "你是一個專業程式開發助手。" + THINK_RULE)
        
        # 🌟 這裡：取代原本單一的 prompt 設定，加入動態判斷！
        if request.mode == "dataset_gen":
            # 把前端傳來的任何需求，加上最後的強迫啟動指令 (Pre-fill)
            prompt = f"【使用者需求與資料格式定義】\n{request.context}\n\n請嚴格依照上述的欄位要求，立刻開始輸出 JSONL，不要廢話，第一個字元必須是：\n"
        else:
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



    
@router.post("/rag_test")
async def run_rag_test(request: RagTestRequest, current_user: Member = Depends(lab_tester_required)):
    is_on_render = os.getenv("RENDER") == "true"
    if is_on_render:
        return {"status": "error", "message": "⚠️ 資安限制：雲端環境已禁用此功能。"}
    
    result = await AdminLabService.run_rag_performance_test(
        query=request.query,
        hnsw_m=request.hnsw_m,
        hnsw_ef=request.hnsw_ef,
        top_k=request.top_k
    )
    hw_status = AdminLabService.get_gpu_status()
    return {**result, **hw_status}


@router.post("/rag_test/log")
async def save_rag_log(
    data: RagLogCreate, 
    db: Session = Depends(get_db), 
    current_user: Member = Depends(lab_tester_required)
):
    try:
        new_log = RagPerformanceLog(
            user_id=current_user.user_id, # ✅ 這裡已經修復為 current_user
            query_text=data.query_text,
            hnsw_m=data.hnsw_m,
            hnsw_ef=data.hnsw_ef,
            retrieval_ms=data.retrieval_ms,
            llm_duration_s=data.llm_duration_s,
            tokens_per_sec=data.tokens_per_sec,
            vram_usage_mb=data.vram_usage_mb,
            gpu_temp=data.gpu_temp,
            total_chunks=data.total_chunks,
            human_score=data.human_score,
            ai_response=data.ai_response
        )
        db.add(new_log)
        db.commit()
        return {"status": "success", "message": "實驗數據已存入"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"儲存失敗: {str(e)}")
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import AIConfig, Member
from ..schemas.ai import AIConfigSave, AIConfigResponse, ChatRequest
from ..dependencies import get_current_user
from ..utils.ai_security import decrypt_api_key
from typing import Optional
import httpx 

router = APIRouter()

# 1. 取得 AI 設定 (保持原樣，讓 Admin 頁面仍能讀取專屬設定)
@router.get("/config", response_model=Optional[AIConfigResponse])
def get_my_config(db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)):
    return db.query(AIConfig).filter(AIConfig.user_id == current_user.user_id, AIConfig.is_active == True).first()

# 2. 儲存設定 (保持原樣，供管理員修改)
@router.post("/config")
def save_ai_config(data: AIConfigSave, db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)):
    db.query(AIConfig).filter(AIConfig.user_id == current_user.user_id).update({"is_active": False})
    from ..utils.ai_security import encrypt_api_key
    secured_key = encrypt_api_key(data.api_key)

    new_config = AIConfig(
        user_id=current_user.user_id,
        provider=data.provider,
        api_key=secured_key,
        base_url=data.base_url,
        model_version=data.model_version,
        system_prompt=data.system_prompt,
        is_active=True
    )
    db.add(new_config)
    db.commit()
    return {"success": True, "message": "AI 設定已安全儲存喵！"}

# 3. AI 對話接口 (【核心修正】：加入自動預設邏輯)
@router.post("/chat")
async def chat_with_meow(req: ChatRequest, db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)):
    print(f"DEBUG: 當前登入 ID 為 {current_user.user_id}")

    # 嘗試抓取該使用者的專屬配置
    config = db.query(AIConfig).filter(
        AIConfig.user_id == current_user.user_id, 
        AIConfig.is_active == True
    ).first()

    # 【重要改動】：如果找不到配置，不噴 400 錯誤，而是直接給它一套預設大腦
    if not config:
        print(f"DEBUG: 使用者 {current_user.user_id} 沒有設定，套用全域預設 Ollama 喵！")
        # 這裡我們手動建立一個虛擬的 config 物件，內容指向你正在跑的 Ollama
        config = AIConfig(
            provider="ollama",
            base_url="http://localhost:11434",
            model_version="gemma3:1b",
            system_prompt=f"你現在是理財助手喵喵。當前使用者是 {current_user.name}。請親切地回答財務問題，說話結尾要帶喵。"
        )

    # 接下來的呼叫邏輯完全相同
    if config.provider == "ollama":
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{config.base_url}/api/chat",
                    json={
                        "model": config.model_version,
                        "messages": [
                            {"role": "system", "content": config.system_prompt},
                            {"role": "user", "content": req.message}
                        ],
                        "stream": False,
                    },
                    timeout=120.0 
                )
                res_data = response.json()
                return {"reply": res_data["message"]["content"]}
            except Exception as e:
                return {"reply": f"喵... 聯絡不到地端 Ollama，請確認它有開啟喵！錯誤：{str(e)}"}
    
    elif config.provider == "gemini":
        # 如果是預設值，這裡的 api_key 會是 None，所以要防呆
        real_key = decrypt_api_key(config.api_key) if config.api_key else None
        return {"reply": "喵！Google 套件更新中，請切換至 Ollama 模式測試喵！"}
    
    return {"reply": "喵喵目前迷路了。"}
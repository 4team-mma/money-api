from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..database import get_db
from ..models import AIConfig, Member, AddRecord
from ..schemas.ai import AIConfigSave, AIConfigResponse, ChatRequest
from ..dependencies import get_current_user
from ..utils.ai_security import decrypt_api_key
from typing import Optional
import httpx 
from datetime import datetime

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
    # 1. 抓取 AI 配置 (預設或專屬)
    config = db.query(AIConfig).filter(AIConfig.user_id == current_user.user_id, AIConfig.is_active == True).first()
    if not config:
        config = AIConfig(provider="ollama", base_url="http://localhost:11434", model_version="gemma3:1b")

    # 2. 【核心升級】：從資料庫抓取使用者的財務上下文
    # A. 計算本月總支出 (add_type=0 為支出)
    this_month = datetime.now().strftime("%Y-%m")
    monthly_expense = db.query(func.sum(AddRecord.add_amount)).filter(
        AddRecord.user_id == current_user.user_id,
        AddRecord.add_type == 0,
        func.date_format(AddRecord.add_date, "%Y-%m") == this_month
    ).scalar() or 0

    # B. 抓取最近 3 筆消費紀錄
    recent_records = db.query(AddRecord).filter(
        AddRecord.user_id == current_user.user_id
    ).order_by(AddRecord.add_date.desc()).limit(3).all()
    
    records_text = "\n".join([f"- {r.add_date}: {r.add_class} 花了 {r.add_amount}元" for r in recent_records])

    # 3. 組合「有記憶」的系統提示詞
    # 我們把使用者的職位、XP 等級、以及剛算好的數據都塞進去
    financial_context = f"""
    當前使用者資訊：
    - 姓名：{current_user.name}
    - 職業：{current_user.job}
    - 修仙等級：Lv.{current_user.level} (XP: {current_user.xp})
    
    財務現況：
    - 本月({this_month})總支出目前為：{float(monthly_expense)} 元。
    - 最近的三筆紀錄：
    {records_text if recent_records else "尚無紀錄"}
    """

    system_prompt = f"""
    你現在是理財助手喵喵。
    以下是使用者的實際財務數據，請根據這些數據回答問題。
    如果使用者問支出，請直接參考下方的數據，不要再問使用者在哪裡紀錄。
    說話結尾務必帶「喵~」。
    
    {financial_context}
    """
    
    # 4. 呼叫 Ollama
    if config.provider == "ollama":
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{config.base_url}/api/chat",
                    json={
                        "model": config.model_version,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": req.message}
                        ],
                        "stream": False,
                    },
                    timeout=120.0 
                )
                res_data = response.json()
                return {"reply": res_data["message"]["content"]}
            except Exception as e:
                return {"reply": f"喵... 聯絡不到 Ollama，錯誤：{str(e)}"}
    
    return {"reply": "喵~ Gemini 功能還在串接中。"}
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Body,Query
from ..dependencies import get_current_user
from ..models import Member
import logging
import json
import httpx
import os
import asyncio
import re
from typing import List, Any, Dict
import hashlib
# 確保路徑對齊你的專案結構
from web_app.services.gemini_service import GeminiService 

router = APIRouter(tags=["第三方服務整合"])
logger = logging.getLogger(__name__)

# =====================================================
# 🧠 STEP 1：只做 Gemini 解析（耗時操作）
# =====================================================
@router.post("/calendar/analyze")
async def analyze_schedule(
    file: UploadFile = File(...),
    current_user: Member = Depends(get_current_user)
):
    content_type = file.content_type
    if not content_type or not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="請上傳圖片喵！")

    try:
        image_bytes = await file.read()
        # 強制 AI 只回傳行程，並明確定義 JSON
        prompt = """
你是一個課表辨識 AI。

請從圖片中解析「所有課程或行程」。

規則：
你是一個課表辨識 AI。請直接輸出 JSON 陣列，不要解釋。
每個物件欄位：
- summary: 課程名稱
- start: {"dateTime": "ISO格式"}
- end: {"dateTime": "ISO格式"}
- period: "上午" 或 "下午" (判斷該行程位於圖片的上半部或下半部)

時間預設：上午 09:00-12:00，下午 13:30-16:30。
"""

        env_key = os.getenv("GEMINI_API_KEY") 
        api_key: str = str(env_key) if env_key else ""

        ai_response = await GeminiService.analyze_image_async(
            api_key=api_key,
            image_bytes=image_bytes,
            mime_type=content_type,
            prompt=prompt
        )
        
        # 提取 JSON
        json_match = re.search(r'\[.*\]', ai_response, re.DOTALL)
        if not json_match:
            # 🌟 修正點：如果沒抓到 JSON，回傳空的陣列而不是崩潰
            return {"success": True, "events": []}
            
        events = json.loads(json_match.group(0))

        processed_events = []
        seen_ids = set()
        
        for e in events:
            summary = e.get('summary', '未命名行程')
            start_time = e.get('start', {}).get('dateTime', '')

            unique_str = f"{summary}_{start_time}"
            event_id = hashlib.md5(unique_str.encode()).hexdigest()

            if event_id in seen_ids:
                continue  

            seen_ids.add(event_id)

            # 🌟 加上去重標籤
            e['extendedProperties'] = {
                "private": {
                    "app_source_id": event_id
                }
            }
            processed_events.append(e)

        # 🌟 關鍵修正：return 必須在 for 迴圈「外面」！！
        return {
            "success": True,
            "events": processed_events
        }

    except Exception as e:
        logger.error(f"AI解析失敗: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# 📅 STEP 2：同步 Google Calendar（批次快速操作）
# =====================================================
@router.post("/calendar/sync")
async def sync_to_google(
    # 使用 Body 接收，Pylance 就不會報 Form 未使用的黃線
    events: List[Dict[str, Any]] = Body(...), 
    google_token: str = Body(...),
    current_user: Member = Depends(get_current_user)
):
    try:
        url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
        headers = {
            "Authorization": f"Bearer {google_token}",
            "Content-Type": "application/json"
        }

        added_count = 0
        skipped_count = 0
        
        # 修正：httpx 異步請求的錯誤處理
        async with httpx.AsyncClient(timeout=30.0) as client:
            for event in events:
                # 1. 取得唯一標籤
                source_id = event.get('extendedProperties', {}).get('private', {}).get('app_source_id')
                
                # 2. 🔍 檢查 Google 是否已有此行程
                if source_id:
                    check_params = {"privateExtendedProperty": f"app_source_id={source_id}"}
                    check_resp = await client.get(url, headers=headers, params=check_params)
                    if check_resp.status_code == 200 and check_resp.json().get('items'):
                        logger.info(f"跳過重複行程: {event.get('summary')}")
                        skipped_count += 1
                        continue

                # 3. 執行新增
                resp = await client.post(url, headers=headers, json=event)
                if resp.status_code in [200, 201]:
                    added_count += 1
                else:
                    logger.warning(f"Google API 寫入失敗: {resp.text}")

        return {
            "success": True,
            "events_added": added_count,
            "events_skipped": skipped_count,
            "total_processed": len(events)
        }

    except Exception as e:
        logger.error(f"同步過程發生系統失敗: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
    
    

# =====================================================
# 🧹 開發專用：清理所有經由 AI 匯入的行程
# =====================================================
@router.delete("/calendar/test-cleanup")
async def clear_google_test_events(
    google_token: str = Query(..., description="Google Access Token"),
    current_user: Member = Depends(get_current_user)
):
    """
    此路由會抓取日曆中所有帶有 'app_source_id' 標記的事件並刪除。
    僅供開發測試重複匯入時使用。
    """
    base_url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    headers = {"Authorization": f"Bearer {google_token}"}
    
    deleted_count = 0
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. 🔍 找出所有含有我們自定義標籤的事件
            # 注意：這裡不指定具體 ID，只過濾含有該屬性的項目
            # 因為 Google API 過濾限制，我們先抓取最近的事件來過濾
            resp = await client.get(base_url, headers=headers)
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail="無法取得 Google 行程")
            
            items = resp.json().get('items', [])
            
            # 2. 判斷哪些事件是我們 App 產生的
            tasks = []
            for item in items:
                private_props = item.get('extendedProperties', {}).get('private', {})
                if 'app_source_id' in private_props:
                    event_id = item.get('id')
                    delete_url = f"{base_url}/{event_id}"
                    tasks.append(client.delete(delete_url, headers=headers))
            
            # 3. 執行批次刪除
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                deleted_count = len([r for r in results if not isinstance(r, Exception)])

        return {
            "success": True, 
            "message": f"清理完成，共刪除 {deleted_count} 筆測試行程喵！"
        }

    except Exception as e:
        logger.error(f"清理腳本執行失敗: {str(e)}")
        raise HTTPException(status_code=500, detail=f"清理失敗: {str(e)}")



@router.get("/calendar/events")
async def get_google_events(
    google_token: str,
    time_min: str, # 格式: 2026-04-01T00:00:00Z
    time_max: str,
    current_user: Member = Depends(get_current_user)
):
    url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    headers = {"Authorization": f"Bearer {google_token}"}
    params = {
        "timeMin": time_min,
        "timeMax": time_max,
        "singleEvents": True,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, params=params)
        items = resp.json().get('items', [])
        
        # 🌟 關鍵：將 Google 格式轉為隊友能讀取的「偽裝」格式
        formatted_events = []
        for item in items:
            start_date = item.get('start', {}).get('dateTime', item.get('start', {}).get('date'))[:10]
            formatted_events.append({
                "add_id": item.get('id'),
                "add_date": start_date,
                "add_class": "📅 行程",
                "add_class_icon": "🗓️",
                "add_member": "Google Calendar",
                "add_note": item.get('summary'),
                "add_amount": 0,    # 行程沒有金額
                "add_type": "event", # 🌟 新增一個 type
                "currency": ""
            })
        return formatted_events
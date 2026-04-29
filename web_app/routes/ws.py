# web_app/routes/ws.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from ..dependencies import get_current_user_ws
from ..models import Member
from ..utils.ws_manager import manager

router = APIRouter()

@router.websocket("/chat")
async def websocket_chat_endpoint(
    websocket: WebSocket,
    current_user: Member = Depends(get_current_user_ws)
):
    """前端一登入就會連上這支 API，保持連線不斷開"""
    user_id = current_user.user_id
    
    # 🌟 使用 getattr 安全取值，避免 Pylance 報錯，預設值給 None
    accepted_subprotocol = getattr(websocket.state, "ws_token", None)
    
    # 🌟 現在 manager.connect 可以合法接收三個參數了，紅線會消失
    await manager.connect(websocket, user_id, accepted_subprotocol)
    
    try:
        while True:
            # 這裡只是為了保持連線，收到什麼都不用特別處理
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)

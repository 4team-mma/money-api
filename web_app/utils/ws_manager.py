# web_app/utils/ws_manager.py
from fastapi import WebSocket
from typing import Dict, List, Optional

class ConnectionManager:
    def __init__(self):
        # 紀錄字典：{ user_id: [WebSocket連線1, WebSocket連線2...] }
        # 這樣如果同一個用戶開了多個網頁，都能收到通知
        self.active_connections: Dict[int, List[WebSocket]] = {}

    # 🌟 將型別標註為 Optional[str] = None，解決 "None" is not assignable to "str" 的錯
    async def connect(self, websocket: WebSocket, user_id: int, subprotocol: Optional[str] = None):
        await websocket.accept(subprotocol=subprotocol)
        
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)

    def disconnect(self, websocket: WebSocket, user_id: int):
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def send_personal_message(self, message: dict, user_id: int):
        """專門發送給指定 user_id 的廣播"""
        if user_id in self.active_connections:
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass

# 建立一個全域實例，讓所有檔案共用同一個總機
manager = ConnectionManager()

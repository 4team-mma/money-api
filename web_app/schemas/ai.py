from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

class AIProvider(str, Enum):
    gemini = "gemini"
    ollama = "ollama"

# 用於「儲存」與「更新」的資料格式
class AIConfigSave(BaseModel):
    provider: AIProvider
    api_key: Optional[str] = None
    base_url: str = "http://localhost:11434"
    model_version: str = "gemma3:1b"
    system_prompt: Optional[str] = "你是一個親切的理財助手喵喵，說話結尾要帶喵~"

# 用於「回傳」給前端的格式 (不包含 API Key)
class AIConfigResponse(BaseModel):
    config_id: int
    provider: str
    base_url: str
    model_version: str
    is_active: bool

    class Config:
        from_attributes = True  # 讓 SQLAlchemy 物件能轉成 Pydantic

# 對話請求格式
class ChatRequest(BaseModel):
    message: str

class ChatMessage(BaseModel):
    role: str # user, assistant, system
    content: str
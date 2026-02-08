# web_app/schemas/ai.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from enum import Enum

class AIProvider(str, Enum):
    gemini = "gemini"
    ollama = "ollama"
    anythingllm = "anythingllm"

class AIConfigSave(BaseModel):
    provider: AIProvider = Field(..., description="模型供應商", examples=["ollama"])
    api_key: Optional[str] = Field(None, description="API 金鑰 (選填)", examples=["your-api-key-here"])
    base_url: str = Field("http://localhost:11434", description="伺服器位址", examples=["http://localhost:11434"])
    model_version: str = Field("gemma3:1b", description="模型版本", examples=["gemma3:1b"])
    system_prompt: Optional[str] = Field(
        "你是一個親切的理財助手喵喵，說話結尾要帶喵~", 
        description="系統提示詞 (人格設定)",
        examples=["你現在是精明的主管喵，專門盯預算。"]
    )

class AIConfigResponse(BaseModel):
    # config_id: int # 註解掉若不需回傳
    provider: str = Field(..., examples=["ollama"])
    base_url: str = Field(..., examples=["http://localhost:11434"])
    model_version: str = Field(..., examples=["gemma3:1b"])
    is_active: bool = Field(..., examples=[True])

    model_config = ConfigDict(from_attributes=True)

class ChatRequest(BaseModel):
    message: str = Field(..., description="使用者輸入的訊息", examples=["幫我分析一下這個月的花費喵"])

class ChatMessage(BaseModel):
    role: str = Field(..., description="角色: user, assistant, system", examples=["user"])
    content: str = Field(..., description="對話內容", examples=["你好喵！"])
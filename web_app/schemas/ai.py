# web_app/schemas/ai.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from enum import Enum

class AIProvider(str, Enum):
    gemini = "gemini"
    ollama = "ollama"
    anythingllm = "anythingllm"

class AIConfigSave(BaseModel):
    provider: AIProvider = Field(..., description="模型供應商", examples=["gemini"])
    # 🔐 api_key 保持選填，因為有時候只是想切換模型而不更新 Key
    api_key: Optional[str] = Field(None, description="API 金鑰 (選填)")
    
    # 🌐 base_url 設為選填 (Optional)，因為 Gemini 走 SDK 不需要此欄位
    base_url: Optional[str] = Field(None, description="伺服器位址 (Ollama/Anything 需要)", examples=["http://localhost:11434"])
    
    # 🤖 model_version 建議給一個通用的預設值
    model_version: str = Field("gemini-1.5-flash", description="模型版本", examples=["gemini-2.0-flash"])
    
    system_prompt: Optional[str] = Field(
        "你是一個親切的理財助手喵喵，說話結尾要帶喵~", 
        description="系統提示詞 (人格設定)"
    )

class AIConfigResponse(BaseModel):
    provider: str = Field(..., examples=["gemini"])
    base_url: Optional[str] = Field(None, examples=["http://localhost:11434"])
    model_version: str = Field(..., examples=["gemini-1.5-flash"])
    system_prompt: Optional[str] = Field(None, description="目前生效的提示詞")
    is_active: bool = Field(..., examples=[True])
    has_key: bool = Field(default=False, description="資料庫是否已存在此供應商的金鑰") # 👈 確保有 default

    model_config = ConfigDict(from_attributes=True)

class ChatRequest(BaseModel):
    message: str = Field(..., description="使用者輸入的訊息")
    persona: str = Field(default="cute", description="喵喵的人格設定")

# 若未來要支援連續對話 (Context)，這會派上用場
class ChatMessage(BaseModel):
    role: str = Field(..., description="角色: user, assistant, system")
    content: str = Field(..., description="對話內容")
    

# line測試用
# Swagger 手動按 Execute，你沒有（也沒辦法手動生出）LINE 伺服器專屬的加密簽章。會有Invalid signature很正常。
class LineWebhookPayload(BaseModel):
    destination: str
    events: list
    
    
# 測試模型用的
class AICompareResultDetail(BaseModel):
    intent: str = Field(..., description="意圖名稱")
    confidence: float = Field(default=1.0, description="信心分數")
    raw_ai_guess: Optional[str] = Field(None, description="模型原始直覺")

class AICompareResponse(BaseModel):
    legacy: AICompareResultDetail = Field(..., description="舊喵喵(關鍵字)結果")
    mix_ai: AICompareResultDetail = Field(..., description="新喵喵(混合)結果")
    review_id: int = Field(..., description="生成的 Log ID，供後續修正用")
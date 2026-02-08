from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional


# 💡 1. 使用者填寫回饋時使用 (維持不變)
class FeedbackCreate(BaseModel):
    feedback_name: str
    question_type: str
    use_page: str
    content: str


# 💡 2. 管理者回覆時使用 (新增)
class FeedbackAdminReply(BaseModel):
    admin_answer: str
    # is_replied 通常在後端邏輯中自動設為 True，所以不一定要由前端傳入


# 💡 3. 後端回傳給前端看的完整格式 (新增欄位)
class FeedbackResponse(BaseModel):
    feedback_id: int
    user_id: int
    feedback_name: str
    question_type: str
    use_page: str
    content: str
    
    # 新增這三個欄位，讓前端能顯示回覆狀態
    admin_answer: Optional[str] = None
    is_replied: int = 0
    replied_at: Optional[datetime] = None
    
    created_at: datetime

    # 啟用 ORM 模式相容性
    model_config = ConfigDict(from_attributes=True)
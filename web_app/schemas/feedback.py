from pydantic import BaseModel
from datetime import datetime
from typing import Optional

# 💡 前端只需要填寫這 4 個欄位
class FeedbackCreate(BaseModel):

    feedback_name: str
    question_type: str
    use_page: str
    content: str

# 💡 後端回傳給前端看的完整資料格式
class FeedbackResponse(BaseModel):

    feedback_id: int
    user_id: int
    feedback_name: str
    question_type: str
    use_page: str
    content: str
    created_at: datetime

class Config:

    from_attributes = True # 允許從 SQLAlchemy 物件直接轉換
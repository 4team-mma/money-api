# web_app/schemas/bot_schema.py
from pydantic import BaseModel, Field
from typing import Optional, List  # 🌟 1. 這裡要引入 List

class FinanceRecordSchema(BaseModel):
    # 這是前端判斷最核心的欄位
    record_type: str = Field(description="必須是 'expense' (支出), 'income' (收入), 或 'transfer' (轉帳) 其中之一")
    
    # 共用欄位
    add_amount: float = Field(description="提取純數字金額，例如 100")
    add_note: str = Field(description="具體項目名稱(如: 拉麵)。若為轉帳且未提理由，預設為'一般轉帳'")
    
    # 支出/收入專用欄位
    add_class: Optional[str] = Field(default="其他", description="支出填'飲食/交通/居家/娛樂'等；收入填'薪資/投資/其他收入'")
    account_name: Optional[str] = Field(default="我的錢包", description="使用者提到的帳戶名稱，例如'台新銀行'")
    add_member: Optional[str] = Field(default="自己", description="幫誰花的，預設為'自己'")
    add_tag: Optional[str] = Field(default="需要", description="預設為'需要'(支出) 或 '意外之財'(收入)")

    # 轉帳專用欄位
    from_account: Optional[str] = Field(default="我的錢包", description="從哪裡轉出")
    to_account: Optional[str] = Field(default="我的錢包", description="轉到哪裡去")
    
# 🌟 新增：雙軌輸出包裝 (同時包含對話與資料)
class RecordResponseSchema(BaseModel):
    reply_text: str = Field(description="用符合 Persona 的可愛喵喵語氣回應小主人，例如：『喵！幫你整理好這筆帳囉，請確認！』")
    
    # 🌟 2. 這裡改成 List，並且給 LLM 下達強烈暗示！
    action_data: List[FinanceRecordSchema] = Field(
        description="要寫入資料庫的嚴格格式資料。必須是一個陣列(List)。如果句子裡有多筆收支，請務必拆分成多個物件填入陣列中。"
    )
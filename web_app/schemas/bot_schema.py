# web_app/schemas/bot_schema.py
from pydantic import BaseModel, Field
from typing import Optional, List  # 🌟 1. 這裡要引入 List

class FinanceRecordSchema(BaseModel):
    # 這是前端判斷最核心的欄位
    record_type: str = Field(
        description="必須是 'expense' (支出), 'income' (收入), 或 'transfer' (轉帳)。"
                    "【極度重要視角規則】：只要句子裡有『花費、購買、付錢』的行為，無論是誰付的錢、買給誰，"
                    "一律判定為 'expense' (支出)！例如：『媽媽買遊戲片給我』是媽媽錢包的支出，千萬不可當作小主人的收入！"
    )

    # 共用欄位
    add_note: str = Field(
        description="具體項目名稱。請盡量保留小主人的原話或活動名稱（例如：'買衣服'、'去爬象山'）。"
                    "【嚴禁過度腦補】：如果小主人沒有明確說這筆錢具體買了什麼（例如只說'去爬山花了65元'），"
                    "請直接填寫'爬山花費'或'象山花費'，絕對不可以自己發明'門票'、'車票'等沒有提到的明細！"
                    "若為轉帳且未提理由，預設為'一般轉帳'。"
    )
    
    # 🌟 日期欄位！讓 AI 有地方填寫推算出來的日期
    record_date: Optional[str] = Field(
        default=None, 
        description=
        "消費日期。格式【嚴格限制為 YYYY-MM-DD】(必須用橫槓 '-' 連接，絕對禁止使用斜線 '/' 或中文字)。\n"
            "請嚴格根據系統時間與小主人的對話（如昨天、前天）推算實際消費日期，例如：2026-04-14。\n"
            "若對話中完全未提及時間，請直接填寫系統當天日期。"
    )
    
    # 🌟 新增：確保金額絕對是數字，防止卡片空白
    add_amount: float = Field(
        description="提取純數字金額（例如：100）。絕對不可以是空值或 0，只要句子裡有提到花費金額就必須填寫。"
    )

    # 支出/收入專用欄位
    # 🌟 修改：把原本寫死的 description 拿掉，告訴它參照 Prompt拿「分類名稱」和「Emoji」
    add_class: Optional[str] = Field(
        default="其他", 
        description="項目類別名稱。請優先使用 Prompt 中提供的專屬分類庫名稱，若無適合的再自行命名(限制4個字內)。"
    )    
    # 🌟 新增：讓 AI 決定 Emoji！
    add_class_icon: Optional[str] = Field(
        default="📦", 
        description="類別對應的 Emoji。請嚴格參照 Prompt 中的合法 Emoji 清單挑選單一符號。"
    )
    account_name: Optional[str] = Field(default="我的錢包", description="使用者提到的帳戶名稱，例如'台新銀行'")
    
    add_member: Optional[str] = Field(
        default="自己", 
        description=
        "這筆錢是『誰的錢包』出去的？也就是這筆帳的『金主』是誰？(例如：自己、媽媽、爸爸、爺爺)。\n"
            "【極度重要判斷規則】：請嚴格根據『誰付錢』來決定成員，而不是『買給誰』！\n"
            "✅ 例子 1：『媽媽買遊戲片給我』 -> 媽媽付錢，成員填『媽媽』。\n"
            "✅ 例子 2：『我買便當給媽媽』 -> 自己付錢，成員填『自己』。\n"
            "若小主人未明確提及是誰付錢，則預設填 '自己'。"
    )    
    # 🌟 新增：教導 AI 標籤的規則與多重標籤寫法
    add_tag: Optional[str] = Field(
        default="需要", 
        description="自訂標籤。必須優先聽從小主人的明確指示(例如：標籤為想要)。如果有多個標籤，請用 '/' 分隔（例如：需要/爬山）。若未提及，支出預設為 '需要'，收入預設為 '意外之財'。"
    )

    # 轉帳專用欄位
    from_account: Optional[str] = Field(default="我的錢包", description="從哪裡轉出")
    to_account: Optional[str] = Field(default="我的錢包", description="轉到哪裡去")

# 🌟 新增：雙軌輸出包裝 (同時包含對話與資料)
class RecordResponseSchema(BaseModel):
    # 🌟 修改：嚴格要求回覆內容必須基於提取出的資料
    reply_text: str = Field(
        description="用符合 Persona 的可愛喵喵語氣回應小主人。"
                    "【極度重要】：請嚴格根據你剛剛提取的 add_note (項目) 與 add_amount (金額) 來撰寫回覆，"
                    "絕對不可以被小主人的背景故事（如生病、出國等前言）誤導而自行發明消費名目！"
                    "例如：『喵！幫你記好買參考書的 200 元囉！』"
    )

    action_data: List[FinanceRecordSchema] = Field(
        description="要寫入資料庫的嚴格格式資料。必須是一個陣列(List)。如果句子裡有多筆收支，請務必拆分成多個物件填入陣列中。"
    )

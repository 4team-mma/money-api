from pydantic import BaseModel, Field, field_validator
from datetime import date, datetime
import re
from typing import Optional, List

# 1. 定義一個內建的驗證函數（Regex），用來檢查發票號碼格式
invoice_number_regex = re.compile(r'^[A-Z]{2}-?\d{8}$')

# 新增：單一商品項目的 schema
class InvoiceItem(BaseModel):
    name: str = Field(..., description="商品名稱")
    quantity: Optional[float] = Field(None, description="數量")
    unit_price: Optional[float] = Field(None, description="單價")
    subtotal: Optional[float] = Field(None, description="小計")

class TaiwanUniformInvoice(BaseModel):
    # --- 基本欄位定义 ---

    # 發票號碼，例如 "AB-11223344"
    # Field 中的 description 會用在自動生成的 API 文件上，很有幫助
    invoice_number: str = Field(..., description="發票號碼，格式為兩位大寫字母+8位數字", examples=["AB-11223344"])

    # 年月，例如 "102年05-06月"
    invoice_period: str = Field(..., description="發票期別", examples=["102年05-06月"])

    # 開立日期，例如 "2013-05-23" (從 2013-05-23 11:22:33 提取)
    # 我們讓 Pydantic 自動把字串轉成 date 物件
    invoice_date: date = Field(..., description="開立日期")

    # 總計金額，例如 "340"
    total_amount: int = Field(..., description="總計金額（新台幣）", gt=0, examples=[340])

    # --- 選擇性欄位（圖片上有，可以選擇存或不存） ---

    # 賣方統一編號，例如 "01234567"
    seller_ban: Optional[str] = Field(None, description="賣方統一編號", min_length=8, max_length=8)

    # 買方統一編號，例如 "09876543"
    buyer_ban: Optional[str] = Field(None, description="買方統一編號", min_length=8, max_length=8)

    # --- 進階自定義驗證 ---
    seller_name: Optional[str] = Field(None, description="賣方名稱/店名")
    items: Optional[List[InvoiceItem]] = Field(
        default=None,
        description="商品明細（二聯式發票或有品項的收據才有）"
    )
    receipt_type: Optional[str] = Field(
        None,
        description="發票種類：電子發票/二聯式/三聯式/收銀機收據/手寫收據"
    )

    @field_validator('invoice_number')
    @classmethod
    def validate_invoice_number(cls, v: str) -> str:
        if not invoice_number_regex.match(v):
            raise ValueError('發票號碼格式錯誤')
        return v

    @field_validator('seller_ban', 'buyer_ban')
    @classmethod
    def validate_ban(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.isdigit():
            raise ValueError('統一編號必須全是數字')
        return v

    # 配置類別，可以設定一些額外的 Pydantic 行為
    model_config = {
        "from_attributes": True, # 🎯 允許從 SQLAlchemy 物件直接讀取資料
        "json_schema_extra": {
            "example": {
                "invoice_number": "AB-11223344",
                "invoice_period": "113年03-04月",
                "invoice_date": "2024-04-02",
                "total_amount": 340,
                "items": [
                    {"name": "拿鐵咖啡", "quantity": 1, "unit_price": 150, "subtotal": 150},
                    {"name": "起司蛋糕", "quantity": 1, "unit_price": 190, "subtotal": 190}
                ]
            }
        }
    }

# --- 測試代碼（看看它如何運作） ---
if __name__ == "__main__":
    # 測試1：傳入正確的發票資料
    correct_data = {
        "invoice_number": "AB-11223344",
        "invoice_period": "102年05-06月",
        "invoice_date": "2013-05-23", # Pydantic 會自動把這裡的字串轉成 date 物件
        "total_amount": "340", # Pydantic 會自動把這裡的字串轉成 int
        "seller_ban": "01234567",
        "buyer_ban": "09876543"
    }
    
    invoice = TaiwanUniformInvoice.model_validate(correct_data)
    print("----- 成功建立的模型 -----")
    print(f"發票號碼: {invoice.invoice_number}")
    print(f"總金額: {invoice.total_amount} (型別: {type(invoice.total_amount)})")
    print(f"日期物件: {invoice.invoice_date} (型別: {type(invoice.invoice_date)})")

    # 測試2：傳入錯誤的資料（格式錯誤）
    wrong_data = {
        "invoice_number": "wrong-num", # 格式不對
        "invoice_period": "102年05-06月",
        "invoice_date": "2013-05-23",
        "total_amount": -100, # 金額不能是負數
        "buyer_ban": "abc" # 統編不能有字母
    }
    
    print("\n----- 預期會發生的錯誤 -----")
    from pydantic import ValidationError
    try:
        TaiwanUniformInvoice(**wrong_data)
    except ValidationError as e:
        print(e)
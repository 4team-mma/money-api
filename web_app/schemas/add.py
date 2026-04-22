from pydantic import BaseModel, Field, ConfigDict  # ConfigDict是將資料庫物件轉成Json
from datetime import date, datetime
from decimal import Decimal  # 處理收支紀錄運算
from typing import Optional, List


# 單筆收支紀錄的詳細資料
class RecordDetail(BaseModel):
    add_id: int
    add_date: date = Field(..., description="日期")
    add_amount: float = Field(..., description="金額")
    add_type: bool = Field(..., description="類型：True 為收入, False 為支出")
    add_class: str = Field(..., description="類別名")
    add_class_icon: str = Field(..., description="類別icon")
    account_id: int = Field(..., description="帳戶ID")
    add_member: str = Field(..., description="成員")
    add_tag: str | None = Field(None, description="標籤")
    add_note: str | None = Field(None, description="備註")
    currency: str = Field(..., description="幣別")
    account_name: str = Field(..., description="帳戶名")
    # 💡 這裡改成 Optional 且預設為 None
    created_at: Optional[datetime] = Field(None, description="建立時間")
    updated_at: Optional[datetime] = Field(None, description="更新時間")

    # Pydantic v2 SQLAlchemy ORM 物件直接轉換
    model_config = ConfigDict(from_attributes=True)


# 前端點擊「儲存」時傳給後端的資料。不包含 id跟userid
class AddRecordCreate(BaseModel):
    add_date: date
    add_amount: Decimal
    add_type: bool
    add_class: str
    add_class_icon: str
    account_id: int
    add_member: str
    add_tag: Optional[str] = None
    add_note: Optional[str] = None

    # 存檔成功後，回傳給前端顯示在清單上的資料。
    # Pydantic v2 的設定寫法，允許從 ORM 物件讀取資料
    model_config = ConfigDict(from_attributes=True)


class AddRecordResponse(AddRecordCreate):
    add_id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# 月度匯總回應模型
class MonthlyRecordResponse(BaseModel):
    success: bool = True
    year: int
    month: int
    total_count: int = Field(..., description="該月紀錄總筆數")
    monthly_income: float = Field(..., description="該月總收入")
    monthly_expenses: float = Field(..., description="該月總支出")
    monthly_balance: float = Field(..., description="該月結餘")
    data: List[RecordDetail] = Field(..., description="詳細收支紀錄清單")


# 修改
class AddRecordUpdate(BaseModel):
    add_date: Optional[date] = None
    add_amount: Optional[Decimal] = None
    add_type: Optional[bool] = None
    add_class: Optional[str] = None
    add_class_icon: Optional[str] = None
    account_id: Optional[int] = None  # 可能會換帳戶扣錢
    add_member: Optional[str] = None
    add_tag: Optional[str] = None
    add_note: Optional[str] = None


#### 這邊是Add_item表格的schemas
# schemas/add.py 新增

class AddItemCreate(BaseModel):
    sort_order: int = 0
    item_name: str
    item_amount: Decimal
    item_class: Optional[str] = None

class AddItemResponse(BaseModel):
    item_id: int
    add_id: int
    sort_order: int
    item_name: str
    item_amount: Decimal
    item_class: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

class AddRecordWithItemsResponse(AddRecordResponse):
    items: List[AddItemResponse] = []
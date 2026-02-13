# web_app/schemas/transfers.py
from pydantic import BaseModel, ConfigDict, Field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List

class AccountInfo(BaseModel):
    account_id: Optional[int] = Field(None, examples=[1])
    account_name: str = Field(..., description="帳戶名", examples=["國泰世華"])
    account_icon: Optional[str] = Field(None, description="帳戶圖示", examples=["🏦"])
    currency: Optional[str] = Field(None, description="幣別", examples=["NT$"])

class TransferDetail(BaseModel):
    transaction_id: int = Field(..., examples=[101])
    transaction_date: date = Field(..., description="日期", examples=["2026-02-08"])
    from_account_id: Optional[int] = Field(None, description="來源帳戶ID", examples=[1])
    to_account_id: Optional[int] = Field(None, description="去向帳戶ID", examples=[2])
    amount: Decimal = Field(..., description="金額", examples=[5000.0])
    transaction_note: Optional[str] = Field(None, description="備註", examples=["儲蓄轉帳"])
    from_account: AccountInfo
    to_account: AccountInfo
    created_at: Optional[datetime] = Field(None, description="建立時間")
    updated_at: Optional[datetime] = Field(None, description="更新時間")
    
    model_config = ConfigDict(from_attributes=True)

class MonthlyTransferResponse(BaseModel):
    success: bool = Field(..., examples=[True])
    year: int = Field(..., examples=[2026])
    month: int = Field(..., examples=[2])
    total_count: int = Field(..., examples=[1])
    data: List[TransferDetail] = Field(..., description="詳細轉帳紀錄清單")

    model_config = ConfigDict(from_attributes=True)

class TransferCreate(BaseModel):
    transaction_date: date = Field(..., description="轉帳日期", examples=["2026-02-08"])
    from_account_id: int = Field(..., description="來源帳戶 ID", examples=[1])
    to_account_id: int = Field(..., description="目標帳戶 ID", examples=[2])
    from_account_name: Optional[str] = Field(None, description="來源帳戶名稱 (選填)", examples=["我的錢包"])
    to_account_name: Optional[str] = Field(None, description="目標帳戶名稱 (選填)", examples=["預設銀行"])
    transaction_note: Optional[str] = Field(None, description="轉帳說明", max_length=200, examples=["零用錢存入"])
    amount: Decimal = Field(..., description="轉帳金額", examples=[1000.5])

class TransferResponse(TransferCreate):
    transaction_id: int = Field(..., examples=[1])
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

class TransferUpdate(BaseModel):
    transaction_date: Optional[date] = Field(None, examples=["2026-02-09"])
    from_account_id: Optional[int] = Field(None, examples=[1])
    to_account_id: Optional[int] = Field(None, examples=[2])
    transaction_note: Optional[str] = Field(None, description="轉帳說明", max_length=200, examples=["更新說明"])
    amount: Optional[Decimal] = Field(None, examples=[1200.0])
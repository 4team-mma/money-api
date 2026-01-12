# web_app/schemas/transfers.py
from pydantic import BaseModel, ConfigDict
from datetime import date
from decimal import Decimal

class TransferCreate(BaseModel):
    transaction_date: date
    from_account_id: int  # 來源帳戶 ID
    to_account_id: int    # 目標帳戶 ID
    amount: Decimal

class TransferResponse(TransferCreate):
    transaction_id: int
    user_id: int
    model_config = ConfigDict(from_attributes=True)
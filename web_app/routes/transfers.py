# web_app/routes/transfers.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Account, Transaction
from ..dependencies import get_current_user_id
from pydantic import BaseModel
from datetime import date
from decimal import Decimal

router = APIRouter()

# 定義接收轉帳的 Schema
class TransferCreate(BaseModel):
    transaction_date: date
    from_account_id: int
    to_account_id: int
    amount: Decimal

@router.post("/")
async def create_transfer(
    data: TransferCreate, 
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    try:
        # 1. 取得並驗證帳戶
        from_acc = db.query(Account).filter(Account.account_id == data.from_account_id, Account.user_id == user_id).first()
        to_acc = db.query(Account).filter(Account.account_id == data.to_account_id, Account.user_id == user_id).first()

        if not from_acc or not to_acc:
            raise HTTPException(status_code=404, detail="轉出或轉入帳戶不存在")
        
        if from_acc.current_balance < data.amount:
            raise HTTPException(status_code=400, detail="轉出帳戶餘額不足")

        # 2. 異動帳戶餘額
        from_acc.current_balance -= data.amount
        to_acc.current_balance += data.amount

        # 3. 寫入 Transactions 表 (根據您的 SQL 結構)
        new_tx = Transaction(
            user_id=user_id,
            transaction_date=data.transaction_date,
            from_account=from_acc.account_name, # 您的 SQL 是儲存名稱
            to_account=to_acc.account_name,
            amount=data.amount
        )
        db.add(new_tx)
        db.commit()
        return {"msg": "轉帳成功", "transaction_id": new_tx.transaction_id}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
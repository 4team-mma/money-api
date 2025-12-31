from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import AddRecord
from ..schemas.add import AddRecordCreate, AddRecordResponse 
from ..models import Account, Transaction
from typing import List
from sqlalchemy import func

# 調用守門員,拿到user_id後進行過濾。

router = APIRouter()

# 2. 💡 這是我們要測試「讀取假資料」的 API
@router.get("/", response_model=List[AddRecordResponse])
async def get_records(db: Session = Depends(get_db)):
    """
    從資料庫抓出所有記帳紀錄，測試連線是否成功
    """
    try:
        # 執行：SELECT * FROM Adds;
        records = db.query(AddRecord).all()
        return records
    except Exception as e:
        # 如果出錯，會回傳錯誤訊息，方便我們排錯
        raise HTTPException(status_code=500, detail=f"資料庫連線出錯：{str(e)}")
    
@router.post("/transfer")
async def create_transfer(user_id: int, from_id: int, to_id: int, amount: float, db: Session = Depends(get_db)):
    try:
        # 1. 找到轉出與轉入帳戶
        from_acc = db.query(Account).filter(Account.account_id == from_id).first()
        to_acc = db.query(Account).filter(Account.account_id == to_id).first()

        if not from_acc or not to_acc:
            raise HTTPException(status_code=404, detail="帳戶不存在")

        # 2. 扣錢與加錢
        from_acc.current_balance -= amount
        to_acc.current_balance += amount

        # 3. 記錄到 Transactions 表
        new_tx = Transaction(
            user_id=user_id,
            from_account=from_acc.account_name,
            to_account=to_acc.account_name,
            amount=amount,
            transaction_date=func.now()
        )
        db.add(new_tx)
        
        # 4. 提交事務 (這步很重要，失敗會全部撤回)
        db.commit()
        return {"msg": "轉帳成功"}
    except Exception as e:
        db.rollback() # 出錯就倒回，保護錢不會莫名消失
        raise HTTPException(status_code=500, detail=str(e))





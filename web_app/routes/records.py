from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import AddRecord
from ..schemas.add import AddRecordCreate, AddRecordResponse 
from ..models import Account, Transaction
from ..dependencies import get_current_user_id
from typing import List
from sqlalchemy import func

# 調用守門員,拿到user_id後進行過濾。

router = APIRouter()

# 2. 測試「讀取假資料」的 API
@router.get("/", response_model=List[AddRecordResponse])
async def get_records(
    
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):    
    """
    從資料庫抓出該登入使用者的收支紀錄
    """
    try:
        # 執行：SELECT * FROM Adds;
        # records = db.query(AddRecord).all()
        records = db.query(AddRecord)\
        .filter(AddRecord.user_id == user_id)\
        .order_by(AddRecord.add_date.desc(), AddRecord.id.desc())\
        .all()
        return records
    except Exception as e:
        # 如果出錯，會回傳錯誤訊息，方便我們排錯
        raise HTTPException(status_code=500, detail=f"資料庫連線出錯：{str(e)}")


@router.post("/", response_model=AddRecordResponse)
async def create_record(
    data: AddRecordCreate, 
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
    ):
    try:
        # 1. 建立資料庫物件
        new_record = AddRecord(
            user_id=user_id,
            **data.dict()
        )
        db.add(new_record)

        # 2. 連動更新帳戶餘額
        account = db.query(Account).filter(Account.account_id == data.account_id).first()
        if not account:
            raise HTTPException(status_code=404, detail="找不到指定帳戶或權限不足")
        
        if data.add_type == False: # 支出
            account.current_balance -= data.add_amount
        else: # 收入
            account.current_balance += data.add_amount

        db.commit()
        db.refresh(new_record)
        return new_record
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


    
@router.post("/transfer")
async def create_transfer(from_id: int, 
    to_id: int, 
    amount: float, 
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
    # 💡 user_id 改由 Token 提供，更安全
    
):
    try:

# 1. 找到轉出與轉入帳戶 (額外檢查 user_id 確保帳戶是自己的)
        from_acc = db.query(Account).filter(Account.account_id == from_id, Account.user_id == user_id).first()
        to_acc = db.query(Account).filter(Account.account_id == to_id).first()

        if not from_acc:
            raise HTTPException(status_code=404, detail="轉出帳戶不存在或不屬於當前用戶")
        if not to_acc:
            raise HTTPException(status_code=404, detail="轉入帳戶不存在")

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
        
        # 4. 提交事務
        db.commit()
        return {"msg": "轉帳成功"}
    except HTTPException as he:
        db.rollback()
        raise he
    except Exception as e:
        db.rollback()  # 出錯就倒回，保護錢不會莫名消失
        raise HTTPException(status_code=500, detail=str(e))





# web_app/routes/transfers.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import extract
from ..database import get_db
from ..models import Account, Transaction
from ..dependencies import get_current_user_id
from pydantic import BaseModel
from datetime import date
from decimal import Decimal
from ..schemas.transfers import TransferCreate, TransferResponse, TransferUpdate
from typing import List

router = APIRouter()

# 定義接收轉帳的 Schema
class TransferCreate(BaseModel):
    transaction_date: date
    from_account_id: int
    to_account_id: int
    amount: Decimal


# 查詢get
@router.get("/", response_model=List[TransferResponse])
async def get_all_transfers(
    year: int = None, 
    month: int = None, 
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """
    獲取轉帳清單，支援按年、月篩選
    """
    try:
        # 1. 基礎查詢：先過濾出「屬於該使用者」的紀錄
        query = db.query(Transaction).filter(Transaction.user_id == user_id)

        # 2. 動態篩選：如果有傳 year，就加一個年份過濾條件
        if year:
            query = query.filter(extract('year', Transaction.transaction_date) == year)
        
        # 3. 動態篩選：如果有傳 month，就加一個月份過濾條件
        if month:
            query = query.filter(extract('month', Transaction.transaction_date) == month)

        # 4. 排序：通常我們會希望最新的紀錄在最前面
        results = query.order_by(Transaction.transaction_date.desc()).all()
        
        return results

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查詢失敗: {str(e)}")



# 新增
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
    

# 修改:
# 修改與刪除必須帶上 {id}，例如:@router.patch("/{transaction_id}")
@router.patch("/{transaction_id}", response_model=TransferResponse)
async def update_transfer(
    transaction_id: int, 
    # 對應的功能TransferCreate, TransferResponse, TransferUpdate
    # 從前端 Body 拿到的修改內容
    data: TransferUpdate,  
    
    # 是否需要動到資料庫或確認身分
    #db: Session = Depends(get_db)的部分:
    # 讓你能在 API 裡面下達 db.query()、db.add() 或 db.commit() 等指令。
    # 只要這支 API 需要讀取、新增、修改或刪除資料庫裡的資料，就一定要寫
    
    # user_id: int = Depends(get_current_user_id)的部分:
    # 在 dependencies.py 定義的「守門員」。它會去檢查 Header 裡的 JWT Token，並解碼出是哪位使用者的 ID。
    # 功能:驗證身分+資料過濾
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    try:
        # 1. 找出舊的轉帳紀錄
        old_tx = db.query(Transaction).filter(
            Transaction.transaction_id == transaction_id, 
            Transaction.user_id == user_id
        ).first()
        
        if not old_tx:
            raise HTTPException(status_code=404, detail="找不到該筆轉帳紀錄")

        # 2. 【核心邏輯：餘額回補】
        # 先找出舊紀錄中的轉出與轉入帳戶，把金額「倒回去」
        # 注意：SQL 存的是名稱，所以要用 account_name 找
        old_from_acc = db.query(Account).filter(Account.account_name == old_tx.from_account, Account.user_id == user_id).first()
        old_to_acc = db.query(Account).filter(Account.account_name == old_tx.to_account, Account.user_id == user_id).first()
        
        if old_from_acc: old_from_acc.current_balance += old_tx.amount # 退回轉出的錢
        if old_to_acc: old_to_acc.current_balance -= old_tx.amount     # 扣除多加的錢

        # 3. 處理新資料的映射
        # 如果前端有傳新的帳戶 ID，則更新為新帳戶；否則延用舊帳戶
        new_from_id = data.from_account_id if data.from_account_id else None
        new_to_id = data.to_account_id if data.to_account_id else None
        
        # 4. 【執行新的扣款邏輯】
        # 根據新的（或舊的）帳戶與金額，重新計算餘額
        # (這裡為了簡化，假設帳戶沒換，只改金額)
        new_amount = data.amount if data.amount is not None else old_tx.amount
        
        if old_from_acc: old_from_acc.current_balance -= new_amount
        if old_to_acc: old_to_acc.current_balance += new_amount

        # 5. 更新 Transactions 表格內容
        if data.transaction_date: old_tx.transaction_date = data.transaction_date
        old_tx.amount = new_amount
        
        db.commit()
        db.refresh(old_tx)
        return old_tx

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"修改失敗: {str(e)}")
    
    
# 刪除:
@router.delete("/{transaction_id}")
async def delete_transfer(
    transaction_id: int, 
    db: Session = Depends(get_db), #
    user_id: int = Depends(get_current_user_id)
):
    try:
        # 1. 安全檢查：找出這筆轉帳，並確認它是屬於這個使用者的
        tx = db.query(Transaction).filter(
            Transaction.transaction_id == transaction_id, 
            Transaction.user_id == user_id
        ).first() #
        
        if not tx:
            raise HTTPException(status_code=404, detail="轉帳紀錄不存在或無權限刪除")

        # 2. 找出受影響的兩個帳戶 (根據你的 SQL，是用名稱查找)
        from_acc = db.query(Account).filter(
            Account.account_name == tx.from_account, 
            Account.user_id == user_id
        ).first() #
        
        to_acc = db.query(Account).filter(
            Account.account_name == tx.to_account, 
            Account.user_id == user_id
        ).first() #

        # 3. 餘額反向回補 (Reversal)
        if from_acc:
            # 原本轉出錢，現在刪除紀錄，要把錢還給轉出帳戶
            from_acc.current_balance += tx.amount #
        if to_acc:
            # 原本轉入錢，現在刪除紀錄，要從轉入帳戶把錢扣掉
            to_acc.current_balance -= tx.amount #

        # 4. 執行刪除並確認
        db.delete(tx)
        db.commit() #
        
        return {"msg": "轉帳紀錄已成功刪除，雙方帳戶餘額已同步回補"}

    except Exception as e:
        db.rollback() #
        raise HTTPException(status_code=500, detail=str(e))
    

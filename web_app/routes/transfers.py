# web_app/routes/transfers.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, aliased
from sqlalchemy import select, extract
from ..database import get_db
from ..models import Account, Transaction, Member
from ..dependencies import get_current_user
from ..schemas.transfers import TransferCreate, TransferResponse, TransferUpdate, MonthlyTransferResponse
from typing import List

router = APIRouter()

# 1. 查詢 GET
@router.get("/", response_model=List[TransferResponse])
async def get_all_transfers(
    year: int | None = None,
    month: int | None = None,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    FromAcc = aliased(Account)
    ToAcc = aliased(Account)
    
    # 建立基礎 Query
    query = db.query(
        Transaction,
        FromAcc.account_name.label("from_name"),
        ToAcc.account_name.label("to_name")
    ).join(FromAcc, Transaction.from_account_id == FromAcc.account_id) \
     .join(ToAcc, Transaction.to_account_id == ToAcc.account_id) \
     .filter(Transaction.user_id == current_user.user_id)

    # 動態篩選
    if year:
        query = query.filter(extract('year', Transaction.transaction_date) == year)
    if month:
        query = query.filter(extract('month', Transaction.transaction_date) == month)

    results = query.order_by(Transaction.transaction_date.desc()).all()
    
    final_data = []
    for tx, f_name, t_name in results:
        data = TransferResponse.model_validate(tx)
        data.from_account_name = f_name
        data.to_account_name = t_name
        final_data.append(data)
    
    return final_data

@router.get(
    "/calendar/monthly",
    summary="取得月度轉帳紀錄",
    response_model=MonthlyTransferResponse,
    response_description="回傳轉帳統計數據與詳細紀錄清單"
)
async def get_monthly_transfers(
    year: int = Query(..., ge=2000, le=2100, description="年份"),
    month: int = Query(..., ge=1, le=12, description="月份"),
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    # 1. 為同一張 Account 表建立兩個別名 (Alias)
    fromAcc = aliased(Account, name="fromAcc")
    toAcc = aliased(Account, name="toAcc")

    # 2. 建立查詢
    stmt = (
        select(
            Transaction,            # 轉帳紀錄主表
            fromAcc.account_name.label("from_account_name"),
            fromAcc.account_icon.label("from_account_icon"),
            fromAcc.currency.label("from_currency"),
            toAcc.account_name.label("to_account_name")
        )
        .join(fromAcc, Transaction.from_account_id == fromAcc.account_id, isouter=True)
        .join(toAcc, Transaction.to_account_id == toAcc.account_id, isouter=True)
        .filter(Transaction.user_id == current_user.user_id)
        .filter(extract('year', Transaction.transaction_date) == year)
        .filter(extract('month', Transaction.transaction_date) == month)
        .order_by(Transaction.transaction_date.desc(), Transaction.transaction_id.desc())
    )

    results = db.execute(stmt).all()

    # 3. 資料格式化與統計
    formatted_data = []
        
    for row in results:
        trans = row[0]  # Transaction ORM 物件
        
        item = {
            "transaction_id": trans.transaction_id,
            "transaction_date": trans.transaction_date,
            "from_account_id": trans.from_account_id,
            "to_account_id": trans.to_account_id,
            "transaction_note": trans.transaction_note,
            "amount": trans.amount,
            # 將轉出帳戶資訊打包成物件
            "from_account": {
                "account_id": trans.from_account_id,
                "account_name": row.from_account_name or "未知帳戶",
                "account_icon": row.from_account_icon,
                "currency": row.from_currency or "N/A"
            },
            
            # 將轉入帳戶資訊打包成物件
            "to_account": {
                "account_id": trans.to_account_id,
                "account_name": row.to_account_name or "未知帳戶"
            }
        }
        formatted_data.append(item)

    return {
        "success": True,
        "year": year,
        "month": month,
        "total_count": len(formatted_data),
        "data": formatted_data
    }

# 2. 新增 POST
@router.post("/")
async def create_transfer(
    data: TransferCreate, 
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    from_acc = db.query(Account).filter(Account.account_id == data.from_account_id, Account.user_id == current_user.user_id).first()
    to_acc = db.query(Account).filter(Account.account_id == data.to_account_id, Account.user_id == current_user.user_id).first()

    if not from_acc or not to_acc:
        raise HTTPException(status_code=404, detail="轉出或轉入帳戶不存在")
        
    if from_acc.current_balance < data.amount:
        raise HTTPException(status_code=400, detail="轉出帳戶餘額不足")

    # 異動餘額
    from_acc.current_balance -= data.amount
    to_acc.current_balance += data.amount

    new_tx = Transaction(
        user_id=current_user.user_id,
        transaction_date=data.transaction_date,
        from_account_id=from_acc.account_id, 
        to_account_id=to_acc.account_id,
        amount=data.amount,
        transaction_note=data.transaction_note
    )
    db.add(new_tx)
    db.commit()
    return {"msg": "轉帳成功", "transaction_id": new_tx.transaction_id}

# 3. 修改 PATCH
@router.patch("/{transaction_id}", response_model=TransferResponse)
async def update_transfer(
    transaction_id: int, 
    data: TransferUpdate,  
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    old_tx = db.query(Transaction).filter(
        Transaction.transaction_id == transaction_id, 
        Transaction.user_id == current_user.user_id
    ).first()
    
    if not old_tx:
        raise HTTPException(status_code=404, detail="找不到該筆轉帳紀錄")

    # 餘額還原
    old_from_acc = db.query(Account).filter(Account.account_id == old_tx.from_account_id, Account.user_id == current_user.user_id).one()
    old_to_acc = db.query(Account).filter(Account.account_id == old_tx.to_account_id, Account.user_id == current_user.user_id).one()
    
    old_from_acc.current_balance += old_tx.amount
    old_to_acc.current_balance -= old_tx.amount

    # 計算新邏輯
    new_from_id = data.from_account_id if data.from_account_id is not None else old_tx.from_account_id
    new_to_id = data.to_account_id if data.to_account_id is not None else old_tx.to_account_id
    new_amount = data.amount if data.amount is not None else old_tx.amount

    new_from_acc = db.query(Account).filter(Account.account_id == new_from_id, Account.user_id == current_user.user_id).one()
    new_to_acc = db.query(Account).filter(Account.account_id == new_to_id, Account.user_id == current_user.user_id).one()

    if new_from_acc.current_balance < new_amount:
        raise HTTPException(status_code=400, detail="轉出帳戶餘額不足，無法修改")

    new_from_acc.current_balance -= new_amount
    new_to_acc.current_balance += new_amount

    # 更新欄位
    old_tx.from_account_id = new_from_id
    old_tx.to_account_id = new_to_id
    old_tx.amount = new_amount
    if data.transaction_date: old_tx.transaction_date = data.transaction_date
    if data.transaction_note is not None: 
        old_tx.transaction_note = data.transaction_note

    db.commit()
    db.refresh(old_tx)
    return old_tx

# 4. 刪除 DELETE
@router.delete("/{transaction_id}")
async def delete_transfer(
    transaction_id: int, 
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    tx = db.query(Transaction).filter(
        Transaction.transaction_id == transaction_id, 
        Transaction.user_id == current_user.user_id
    ).first()
    
    if not tx:
        raise HTTPException(status_code=404, detail="轉帳紀錄不存在或無權限刪除")

    from_acc = db.query(Account).filter(Account.account_id == tx.from_account_id, Account.user_id == current_user.user_id).first()
    to_acc = db.query(Account).filter(Account.account_id == tx.to_account_id, Account.user_id == current_user.user_id).first()

    if from_acc: from_acc.current_balance += tx.amount
    if to_acc: to_acc.current_balance -= tx.amount

    db.delete(tx)
    db.commit()
    return {"msg": "轉帳紀錄已成功刪除，雙方帳戶餘額已同步回補"}
# web_app/routes/transfers.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, aliased
from sqlalchemy import select, extract
from ..database import get_db
from ..models import Account, Transaction, Member
from ..dependencies import get_current_user
from ..schemas.transfers import (
    TransferCreate,
    TransferResponse,
    TransferUpdate,
    MonthlyTransferResponse,
)
from typing import List

router = APIRouter()

# 1. 查詢所有轉帳紀錄
@router.get("/", response_model=List[TransferResponse], summary="🔍 查詢所有轉帳紀錄")
async def get_all_transfers(
    year: int | None = Query(None, description="篩選年份", examples=[2026]),
    month: int | None = Query(None, description="篩選月份", examples=[2]),
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    """
    取得目前使用者的所有轉帳紀錄，並支援年月篩選。

    - **功能**:
        - 自動關聯「轉出」與「轉入」帳戶名稱。
        - 預設按日期由新到舊排序。
    - **篩選**: 若未提供 year/month，則回傳歷史所有紀錄。
    """
    FromAcc = aliased(Account)
    ToAcc = aliased(Account)

    query = (
        db.query(
            Transaction,
            FromAcc.account_name.label("from_name"),
            ToAcc.account_name.label("to_name"),
        )
        .join(FromAcc, Transaction.from_account_id == FromAcc.account_id)
        .join(ToAcc, Transaction.to_account_id == ToAcc.account_id)
        .filter(Transaction.user_id == current_user.user_id)
    )

    if year:
        query = query.filter(extract("year", Transaction.transaction_date) == year)
    if month:
        query = query.filter(extract("month", Transaction.transaction_date) == month)

    results = query.order_by(Transaction.transaction_date.desc()).all()

    final_data = []
    for tx, f_name, t_name in results:
        data = TransferResponse.model_validate(tx)
        data.from_account_name = f_name
        data.to_account_name = t_name
        final_data.append(data)

    return final_data

# 2. 取得月度轉帳統計
@router.get(
    "/calendar/monthly",
    summary="📅 取得月度統計與清單",
    response_model=MonthlyTransferResponse
)
async def get_monthly_transfers(
    year: int = Query(..., ge=2000, le=2100, description="年份", examples=[2026]),
    month: int = Query(..., ge=1, le=12, description="月份", examples=[2]),
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    """
    專為日曆或月統計頁面設計的接口。

    - **回傳結構**:
        - `total_count`: 該月總轉帳筆數。
        - `data`: 詳細清單，包含帳戶圖示 (Icon) 與幣別。
    - **特色**: 資料採打包格式 (Nested Object)，適合前端 Vue 組件直接綁定。
    """
    fromAcc = aliased(Account, name="fromAcc")
    toAcc = aliased(Account, name="toAcc")

    stmt = (
        select(
            Transaction,
            fromAcc.account_name.label("from_account_name"),
            fromAcc.account_icon.label("from_account_icon"),
            fromAcc.currency.label("from_currency"),
            toAcc.account_name.label("to_account_name"),
        )
        .join(fromAcc, Transaction.from_account_id == fromAcc.account_id, isouter=True)
        .join(toAcc, Transaction.to_account_id == toAcc.account_id, isouter=True)
        .filter(Transaction.user_id == current_user.user_id)
        .filter(extract("year", Transaction.transaction_date) == year)
        .filter(extract("month", Transaction.transaction_date) == month)
        .order_by(Transaction.transaction_date.desc(), Transaction.transaction_id.desc())
    )

    results = db.execute(stmt).all()
    formatted_data = []

    for row in results:
        trans = row[0]
        item = {
            "transaction_id": trans.transaction_id,
            "transaction_date": trans.transaction_date,
            "from_account_id": trans.from_account_id,
            "to_account_id": trans.to_account_id,
            "transaction_note": trans.transaction_note,
            "amount": trans.amount,
            "created_at": trans.created_at,
            "from_account": {
                "account_id": trans.from_account_id,
                "account_name": row.from_account_name or "未知帳戶",
                "account_icon": row.from_account_icon,
                "currency": row.from_currency or "N/A",
            },
            "to_account": {
                "account_id": trans.to_account_id,
                "account_name": row.to_account_name or "未知帳戶",
            },
        }
        formatted_data.append(item)

    return {
        "success": True,
        "year": year,
        "month": month,
        "total_count": len(formatted_data),
        "data": formatted_data,
    }

# 3. 新增轉帳紀錄
@router.post("/", summary="➕ 新增轉帳紀錄", status_code=status.HTTP_201_CREATED)
async def create_transfer(
    data: TransferCreate,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    """
    建立一筆新的轉帳紀錄，並同步更新相關帳戶餘額。

    - **邏輯流程**:
        1. 驗證來源/目標帳戶是否屬於該用戶。
        2. 檢查轉出帳戶**餘額是否充足**。
        3. 執行餘額異動 (A 減 B 加)。
        4. 寫入交易紀錄。
    - **資安**: 防止越權操作（不可使用他人帳戶 ID 進行轉帳）。
    """
    from_acc = db.query(Account).filter(Account.account_id == data.from_account_id, Account.user_id == current_user.user_id).first()
    to_acc = db.query(Account).filter(Account.account_id == data.to_account_id, Account.user_id == current_user.user_id).first()

    if not from_acc or not to_acc:
        raise HTTPException(status_code=404, detail="轉出或轉入帳戶不存在")

    if from_acc.current_balance < data.amount:
        raise HTTPException(status_code=400, detail="轉出帳戶餘額不足")

    from_acc.current_balance -= data.amount
    to_acc.current_balance += data.amount

    new_tx = Transaction(
        user_id=current_user.user_id,
        transaction_date=data.transaction_date,
        from_account_id=from_acc.account_id,
        to_account_id=to_acc.account_id,
        amount=data.amount,
        transaction_note=data.transaction_note,
    )
    db.add(new_tx)
    db.commit()
    return {"msg": "轉帳成功", "transaction_id": new_tx.transaction_id}

# 4. 修改轉帳紀錄
@router.patch("/{transaction_id}", response_model=TransferResponse, summary="✏️ 修改轉帳紀錄")
async def update_transfer(
    transaction_id: int,
    data: TransferUpdate,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    """
    修改已存在的轉帳紀錄，並自動修正歷史餘額差額。

    - **餘額還原機制**: 系統會先將舊紀錄的金額「倒回去」，再根據新金額進行計算。
    - **檢查限制**: 修改後的轉出帳戶餘額仍不得低於 0。
    """
    old_tx = db.query(Transaction).filter(Transaction.transaction_id == transaction_id, Transaction.user_id == current_user.user_id).first()
    if not old_tx:
        raise HTTPException(status_code=404, detail="找不到該筆轉帳紀錄")

    old_from_acc = db.query(Account).filter(Account.account_id == old_tx.from_account_id, Account.user_id == current_user.user_id).one()
    old_to_acc = db.query(Account).filter(Account.account_id == old_tx.to_account_id, Account.user_id == current_user.user_id).one()

    # 餘額還原
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
    if data.transaction_date:
        old_tx.transaction_date = data.transaction_date
    if data.transaction_note is not None:
        old_tx.transaction_note = data.transaction_note

    db.commit()
    db.refresh(old_tx)
    return old_tx

# 5. 刪除轉帳紀錄
@router.delete("/{transaction_id}", summary="🗑️ 刪除轉帳紀錄")
async def delete_transfer(
    transaction_id: int,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    """
    刪除一筆轉帳紀錄，並將金額同步回補至原帳戶。

    - **回補邏輯**: 轉出帳戶「加回」金額，轉入帳戶「減去」金額。
    - **注意**: 若轉入帳戶餘額不足扣回，仍會強制扣除（可能導致負數，維持會計一致性）。
    """
    tx = db.query(Transaction).filter(Transaction.transaction_id == transaction_id, Transaction.user_id == current_user.user_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="轉帳紀錄不存在或無權限刪除")

    from_acc = db.query(Account).filter(Account.account_id == tx.from_account_id, Account.user_id == current_user.user_id).first()
    to_acc = db.query(Account).filter(Account.account_id == tx.to_account_id, Account.user_id == current_user.user_id).first()

    if from_acc: from_acc.current_balance += tx.amount
    if to_acc: to_acc.current_balance -= tx.amount

    db.delete(tx)
    db.commit()
    return {"msg": "轉帳紀錄已成功刪除，雙方帳戶餘額已同步回補"}
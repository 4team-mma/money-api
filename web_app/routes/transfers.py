# web_app/routes/transfers.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session,aliased # 同一張表格被關聯兩次使用aliased
from sqlalchemy import extract
from ..database import get_db
from ..models import Account, Transaction,Member
from ..dependencies import get_current_user
from ..schemas.transfers import TransferCreate, TransferResponse, TransferUpdate
from typing import List

router = APIRouter()

# 查詢get
@router.get("/", response_model=List[TransferResponse])
async def get_all_transfers(
    year: int = None, 
    month: int = None, 
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    """
    獲取轉帳清單，支援按年、月篩選
    """
    # 1. 為帳戶表建立兩個分身
    FromAcc = aliased(Account)
    ToAcc = aliased(Account)
    
    # 2. 執行 Join 查詢
    # 直接在基礎查詢中加入 Join 與 Label，這樣邏輯更清晰
    query = db.query(
        Transaction,
        FromAcc.account_name.label("from_name"),
        ToAcc.account_name.label("to_name")
    ).join(FromAcc, Transaction.from_account_id == FromAcc.account_id) \
    .join(ToAcc, Transaction.to_account_id == ToAcc.account_id) \
    .filter(Transaction.user_id == current_user.user_id)

    # 3. 動態篩選：年份
    if year:
        query = query.filter(extract('year', Transaction.transaction_date) == year)
    
    # 4. 動態篩選：月份
    if month:
        query = query.filter(extract('month', Transaction.transaction_date) == month)

    # 5. 排序並執行
    results = query.order_by(Transaction.transaction_date.desc()).all()
    
    # 6. 將查詢結果重新打包成 Schema 格式
    final_data = []
    for tx, f_name, t_name in results:
        data = TransferResponse.model_validate(tx)
        data.from_account_name = f_name # 賦予中文名稱
        data.to_account_name = t_name   # 賦予中文名稱
        final_data.append(data)
    
    return final_data

# 新增
@router.post("/")
async def create_transfer(
    data: TransferCreate, 
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    # 1. 取得並驗證帳戶
    from_acc = db.query(Account).filter(Account.account_id == data.from_account_id, Account.user_id == current_user.user_id).first()
    to_acc = db.query(Account).filter(Account.account_id == data.to_account_id, Account.user_id == current_user.user_id).first()

    if not from_acc or not to_acc:
        raise HTTPException(status_code=404, detail="轉出或轉入帳戶不存在")
        
    if from_acc.current_balance < data.amount:
        raise HTTPException(status_code=400, detail="轉出帳戶餘額不足")

    # 2. 異動帳戶餘額
    from_acc.current_balance -= data.amount
    to_acc.current_balance += data.amount

    # 3. 寫入 Transactions 表 (根據您的 SQL 結構)
    new_tx = Transaction(
        user_id=current_user.user_id,
        transaction_date = data.transaction_date,
        from_account_id = from_acc.account_id, 
        to_account_id = to_acc.account_id,
        amount = data.amount
    )
    db.add(new_tx)
    db.commit()
    return {"msg": "轉帳成功", "transaction_id": new_tx.transaction_id}

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
    
    # current_user: Member = Depends(get_current_user)的部分:
    # 在 dependencies.py 定義的「守門員」。它會去檢查 Header 裡的 JWT Token，並解碼出是哪位使用者的 ID。
    # 功能:驗證身分+資料過濾
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    # 1. 找出舊的轉帳紀錄
    old_tx = db.query(Transaction).filter(
        Transaction.transaction_id == transaction_id, 
        Transaction.user_id == current_user.user_id
    ).first()
    
    if not old_tx:
        raise HTTPException(status_code=404, detail="找不到該筆轉帳紀錄")

    # 2. 【第一步：徹底還原舊帳戶餘額】
    # 不管有沒有要換帳戶，先把舊的錢「退回」舊帳戶
    old_from_acc = db.query(Account).filter(Account.account_id == old_tx.from_account_id, Account.user_id == current_user.user_id).one()
    old_to_acc = db.query(Account).filter(Account.account_id == old_tx.to_account_id, Account.user_id == current_user.user_id).one()
    
    old_from_acc.current_balance += old_tx.amount # 退回轉出的錢
    old_to_acc.current_balance -= old_tx.amount     # 扣掉轉入的錢

    # 3. 【第二步：決定新帳戶與新金額】
    # 如果前端有傳新的帳戶 ID，則更新為新帳戶；否則延用舊帳戶
    new_from_id = data.from_account_id if data.from_account_id is not None else old_tx.from_account_id
    new_to_id = data.to_account_id if data.to_account_id is not None else old_tx.to_account_id
    new_amount = data.amount if data.amount is not None else old_tx.amount

    # 4. 【第三步：執行新帳戶的扣款/入帳】
    # 這裡重新撈取「最終選定」的帳戶物件
    new_from_acc = db.query(Account).filter(Account.account_id == new_from_id, Account.user_id == current_user.user_id).one()
    new_to_acc = db.query(Account).filter(Account.account_id == new_to_id, Account.user_id == current_user.user_id).one()

    # 檢查餘額是否足夠 (業務邏輯錯誤，手動拋出 400)
    if new_from_acc.current_balance < new_amount:
        raise HTTPException(status_code=400, detail="轉出帳戶餘額不足，無法修改")

    new_from_acc.current_balance -= new_amount
    new_to_acc.current_balance += new_amount

    # 5. 【第四步：更新交易紀錄表】
    old_tx.from_account_id = new_from_id
    old_tx.to_account_id = new_to_id
    old_tx.amount = new_amount
    if data.transaction_date: 
        old_tx.transaction_date = data.transaction_date
    if data.note is not None:
        old_tx.note = data.note

    # 6. 提交 (若以上過程任何一處出錯，全域處理器會攔截並自動 Rollback)
    db.commit()
    db.refresh(old_tx)
    return old_tx


# 刪除:
@router.delete("/{transaction_id}")
async def delete_transfer(
    transaction_id: int, 
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    # 1. 安全檢查：找出這筆轉帳，並確認它是屬於這個使用者的
    tx = db.query(Transaction).filter(
        Transaction.transaction_id == transaction_id, 
        Transaction.user_id == current_user.user_id
    ).first()
    
    if not tx:
        raise HTTPException(status_code=404, detail="轉帳紀錄不存在或無權限刪除")

    # 2. 找出受影響的兩個帳戶 (根據你的 SQL，是用id查找)
    from_acc = db.query(Account).filter(
        Account.account_id == tx.from_account_id, 
        Account.user_id == current_user.user_id
    ).first()
    
    to_acc = db.query(Account).filter(
        Account.account_id == tx.to_account_id, 
        Account.user_id == current_user.user_id
    ).first()

    # 3. 餘額反向回補 (Reversal)
    if from_acc:
        # 原本轉出錢，現在刪除紀錄，要把錢還給轉出帳戶
        from_acc.current_balance += tx.amount
    if to_acc:
        # 原本轉入錢，現在刪除紀錄，要從轉入帳戶把錢扣掉
        to_acc.current_balance -= tx.amount

    # 4. 執行刪除並確認
    db.delete(tx)
    db.commit()
    
    return {"msg": "轉帳紀錄已成功刪除，雙方帳戶餘額已同步回補"}

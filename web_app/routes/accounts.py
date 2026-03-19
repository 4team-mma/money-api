from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from ..schemas.accounts import AccountCreate, AccountResponse, AccountUpdate
from ..models import Account, Member, AddRecord, Transaction
from ..database import get_db
from ..dependencies import get_current_user

router = APIRouter()

# ===== GET 所有帳戶 =====
@router.get(
    "/", 
    response_model=List[AccountResponse], 
    summary="取得所有帳戶清單",
    description="根據目前登入的使用者資訊，抓取該用戶名下建立的所有資產帳戶，包括帳戶名稱、幣別及目前餘額。",
    response_description="成功回傳該使用者的帳戶列表"
)
def get_accounts(
    db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)
):
    return db.query(Account).filter(Account.user_id == current_user.user_id).all()


# ===== POST 新增帳戶 =====
@router.post(
    "/", 
    response_model=AccountResponse, 
    status_code=status.HTTP_201_CREATED,
    summary="建立新帳戶",
    description="建立一個新的資產帳戶。系統會自動將初始餘額 (initial_balance) 設定為目前餘額 (current_balance)，並與當前使用者綁定。",
    response_description="成功建立並回傳完整的帳戶物件資訊"
)
def create_account(
    account_in: AccountCreate,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    account_data = account_in.model_dump()
    account_data["user_id"] = current_user.user_id

    # --- 新增這段邏輯來修正負債 Bug ---
    # 定義哪些 value 屬於負債類別
    liability_types = ['credit', 'loan', 'installment', 'debt_other']

    # 取得初始金額（確保是正數 abs，避免使用者重複輸入負號造成變正值）
    initial_val = abs(account_in.initial_balance)

    if account_in.account_type in liability_types:
        # 如果是負債，存進去必須是負值
        account_data["current_balance"] = -initial_val
        account_data["initial_balance"] = -initial_val # 初始金額也建議同步為負，方便後續計算
    else:
        account_data["current_balance"] = initial_val



    new_account = Account(**account_data)

    db.add(new_account)
    db.commit()
    db.refresh(new_account)
    return new_account


# ===== DELETE 刪除帳戶 =====
@router.delete(
    "/{account_id}", 
    status_code=status.HTTP_204_NO_CONTENT,
    summary="刪除指定帳戶",
    description="永久刪除指定的帳戶。執行前會嚴格檢查帳戶歸屬權，若非該帳戶擁有者將無法刪除。",
    response_description="成功刪除，無回傳內容"
)
def delete_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    # 1. 查找帳戶
    account_query = db.query(Account).filter(
        Account.account_id == account_id, 
        Account.user_id == current_user.user_id
    )
    account = account_query.first()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="找不到該帳戶或無權限操作"
        )

    try:
        # 2. 刪除相關的收支紀錄 (AddRecords) -> 這些通常跟隨帳戶消失
        db.query(AddRecord).filter(AddRecord.account_id == account_id).delete(synchronize_session=False)

        # 3. 斷開轉帳連結 (Transactions) -> 不刪除紀錄，只將相關欄位設為 NULL
        # 將由此帳戶轉出的轉帳，來源設為 NULL
        db.query(Transaction).filter(Transaction.from_account_id == account_id).update(
            {Transaction.from_account_id: None}, synchronize_session=False
        )
        # 將轉入此帳戶的轉帳，目標設為 NULL
        db.query(Transaction).filter(Transaction.to_account_id == account_id).update(
            {Transaction.to_account_id: None}, synchronize_session=False
        )

        # 4. 刪除帳戶本身
        account_query.delete(synchronize_session=False)

        # 提交所有變更
        db.commit()

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"刪除失敗，資料庫發生錯誤: {str(e)}"
        )

    return None


# ===== PUT 更新帳戶 =====
@router.put(
    "/{account_id}", 
    response_model=AccountResponse,
    summary="修改帳戶內容",
    description="更新現有帳戶的詳細資訊（如名稱、圖示等）。此端點僅會更新 Request Body 中有傳送的欄位，未傳送的欄位將保持原樣。",
    response_description="回傳修改過後的完整帳戶資訊"
)
def update_account(
    account_id: int,
    obj_in: AccountUpdate,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    db_obj = (
        db.query(Account)
        .filter(
            Account.account_id == account_id, Account.user_id == current_user.user_id
        )
        .first()
    )

    if not db_obj:
        raise HTTPException(status_code=404, detail="找不到帳戶或無權限修改")

    update_data = obj_in.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(db_obj, field, value)

    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj
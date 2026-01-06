from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import AddRecord, Account, Transaction
from ..schemas.add import AddRecordCreate, AddRecordResponse, AddRecordUpdate
from ..dependencies import get_current_user_id
from typing import List, Optional
from sqlalchemy import func, or_
from decimal import Decimal
from datetime import date
import math # 🌟 用於計算總頁數

router = APIRouter()

# 1. 讀取紀錄 API (支援分頁與搜尋)
@router.get("/")
async def get_records(
    page: int = 1,              # 預設第 1 頁
    page_size: int = 10,        # 每頁 10 筆
    search: Optional[str] = None, # 搜尋關鍵字
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):    
    try:
        # 建立基礎查詢
        query = db.query(AddRecord).filter(AddRecord.user_id == user_id)

        # 🌟 搜尋邏輯：如果前端有傳搜尋字串，就對 備註、類別、成員 進行模糊比對
        if search:
            query = query.filter(
                or_(
                    AddRecord.add_note.ilike(f"%{search}%"),
                    AddRecord.add_class.ilike(f"%{search}%"),
                    AddRecord.add_member.ilike(f"%{search}%")
                )
            )

        # 🌟 計算總筆數
        total_count = query.count()

        # 🌟 執行分頁
        records = query.order_by(AddRecord.add_date.desc(), AddRecord.id.desc())\
            .limit(page_size)\
            .offset((page - 1) * page_size)\
            .all()

        # 🌟 計算總頁數
        total_pages = math.ceil(total_count / page_size) if total_count > 0 else 1

        # 返回符合 Vue 前端 fetchTransactions 需求的格式
        return {
            "success": True,
            "data": records,
            "pagination": {
                "current_page": page,
                "page_size": page_size,
                "total_rows": total_count,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"資料庫連線出錯：{str(e)}")

# 2. 本月收支統計 API (放在 /{record_id} 之前，避免路徑匹配錯誤)
@router.get("/stats/monthly")
async def get_monthly_stats(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    try:
        today = date.today()
        first_day = today.replace(day=1)

        expense = db.query(func.sum(AddRecord.add_amount))\
            .filter(
                AddRecord.user_id == user_id,
                AddRecord.add_type == False,
                AddRecord.add_date >= first_day
            ).scalar() or Decimal("0")

        income = db.query(func.sum(AddRecord.add_amount))\
            .filter(
                AddRecord.user_id == user_id,
                AddRecord.add_type == True,
                AddRecord.add_date >= first_day
            ).scalar() or Decimal("0")

        return {
            "month": today.strftime("%Y-%m"),
            "total_expense": float(expense),
            "total_income": float(income),
            "net_savings": float(income - expense)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"統計計算失敗：{str(e)}")

# 3. 新增收支紀錄 API
@router.post("/", response_model=AddRecordResponse)
async def create_record(
    data: AddRecordCreate, 
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    try:
        amt_decimal = Decimal(str(data.add_amount))
        new_record = AddRecord(
            user_id=user_id,
            **data.dict()
        )
        db.add(new_record)
        
        account = db.query(Account).filter(Account.account_id == data.account_id).first()
        if account is None:
            raise HTTPException(status_code=404, detail="找不到指定帳戶")
        
        if data.add_type == False: # 支出
            account.current_balance -= amt_decimal
        else: # 收入
            account.current_balance += amt_decimal

        db.commit()
        db.refresh(new_record)
        return new_record
    except HTTPException as he:
        db.rollback()
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# 4. 修改紀錄 API (PATCH)
@router.patch("/{record_id}", response_model=AddRecordResponse)
async def update_record(
    record_id: int,
    data: AddRecordUpdate,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    try:
        db_record = db.query(AddRecord).filter(AddRecord.id == record_id, AddRecord.user_id == user_id).first()
        if not db_record:
            raise HTTPException(status_code=404, detail="找不到該筆紀錄")

        # 1. 還原舊影響
        old_account = db.query(Account).filter(Account.account_id == db_record.account_id).first()
        if old_account:
            if db_record.add_type is False:
                old_account.current_balance += db_record.add_amount
            else:
                old_account.current_balance -= db_record.add_amount

        # 2. 更新資料
        update_data = data.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_record, key, value)
        
        db_record.add_amount = Decimal(str(db_record.add_amount))

        # 3. 套用新影響
        new_account = db.query(Account).filter(Account.account_id == db_record.account_id).first()
        if not new_account:
            db.rollback()
            raise HTTPException(status_code=404, detail="目標帳戶不存在")
            
        if db_record.add_type is False:
            new_account.current_balance -= db_record.add_amount
        else:
            new_account.current_balance += db_record.add_amount

        db.commit()
        db.refresh(db_record)
        return db_record

    except HTTPException as he:
        db.rollback()
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# 5. 刪除紀錄 API
@router.delete("/{record_id}")
async def delete_record(
    record_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    try:
        record = db.query(AddRecord).filter(AddRecord.id == record_id, AddRecord.user_id == user_id).first()
        if record is None:
            raise HTTPException(status_code=404, detail="紀錄不存在或無權限刪除")

        account = db.query(Account).filter(Account.account_id == record.account_id).first()
        if account:
            if record.add_type is False:
                account.current_balance += record.add_amount
            else:
                account.current_balance -= record.add_amount

        db.delete(record)
        db.commit()
        return {"msg": "紀錄已成功刪除，帳戶餘額已同步更新"}
    except HTTPException as he:
        db.rollback()
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# 6. 轉帳 API
@router.post("/transfer")
async def create_transfer(
    from_id: int, 
    to_id: int, 
    amount: float, 
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    try:
        amt_decimal = Decimal(str(amount))
        # 安全檢查：確保轉出帳戶屬於當前使用者 
        from_acc = db.query(Account).filter(Account.account_id == from_id, Account.user_id == user_id).first()
        to_acc = db.query(Account).filter(Account.account_id == to_id).first()

        if from_acc is None:
            raise HTTPException(status_code=404, detail="轉出帳戶不存在或不屬於當前用戶")
        if to_acc is None:
            raise HTTPException(status_code=404, detail="轉入帳戶不存在")
            
        if from_acc.current_balance < amt_decimal:
            raise HTTPException(status_code=400, detail="轉出帳戶餘額不足")

        from_acc.current_balance -= amt_decimal
        to_acc.current_balance += amt_decimal

        new_tx = Transaction(
            user_id=user_id,
            from_account=from_acc.account_name,
            to_account=to_acc.account_name,
            amount=amt_decimal,
            transaction_date=func.now()
        )
        db.add(new_tx)
        
        db.commit()
        return {"msg": "轉帳成功", "amount": float(amt_decimal)}
        
    except HTTPException as he:
        db.rollback()
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
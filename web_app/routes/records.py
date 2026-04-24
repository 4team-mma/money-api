## records.py
from fastapi import APIRouter, Depends, HTTPException, Query,UploadFile,File,Form
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import AddRecord, Account, Member
from web_app.models.models import SavingsGoal,AddItem
from ..schemas.add import (
    AddRecordCreate,
    AddRecordResponse,
    AddRecordUpdate,
    MonthlyRecordResponse,
)
from fastapi import Depends
from ..dependencies import get_current_user
from typing import Optional,List
from sqlalchemy import func, or_, select, and_, extract
from decimal import Decimal
from datetime import date, timedelta
from web_app.services.records_service import RecordsService
from web_app.services.gemini_service import GeminiService
import math  #  用於計算總頁數
router = APIRouter()



# 1. 讀取紀錄 API (支援分頁與搜尋)
@router.get("/")
async def get_records(
    page: int = 1,  # 預設第 1 頁
    page_size: int = 10,  # 每頁 10 筆
    search: Optional[str] = None,  # 搜尋關鍵字
    year: Optional[int] = None,  # 新增年份篩選
    month: Optional[int] = None,  # 新增月份篩選
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    # 建立基礎查詢
    query = db.query(AddRecord).filter(AddRecord.user_id == current_user.user_id)

    # 搜尋邏輯：如果前端有傳搜尋字串，就對 備註、類別、成員 進行模糊比對
    if search:
        query = query.filter(
            or_(
                AddRecord.add_note.ilike(f"%{search}%"),
                AddRecord.add_class.ilike(f"%{search}%"),
                AddRecord.add_member.ilike(f"%{search}%"),
            )
        )
    # 時間篩選邏輯 (與 transfers.py 一致)
    if year:
        query = query.filter(extract("year", AddRecord.add_date) == year)
    if month:
        query = query.filter(extract("month", AddRecord.add_date) == month)
    #  計算總筆數
    total_count = query.count()

    #  執行分頁
    records = (
        query.order_by(AddRecord.add_date.desc(), AddRecord.add_id.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
        .all()
    )

    #  計算總頁數
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
        "has_prev": page > 1,
        },
    }


@router.get(
    "/calendar/monthly",
    summary="取得月度收支清單",
    description="""
根據指定的 **年份** 與 **月份**，查詢該使用者在該月的所有收支紀錄。
- **計算功能**：自動加總該月總收入、總支出與餘額。
- **資料排序**：預設按日期降序 (Newest First)。
- **關聯查詢**：自動關聯帳戶資訊 (如貨幣、帳戶名稱)。
    """,
    response_model=MonthlyRecordResponse,  # 指定回應模型(使用 Pydantic 自動轉換)
    response_description="回傳月度統計數據與詳細紀錄清單",
)
async def get_monthly_records(
    # 讓前端傳遞年份與月份，預設為空則由後端邏輯處理或回傳錯誤
    year: int = Query(..., ge=2000, le=2100, description="年份"),
    month: int = Query(..., ge=1, le=12, description="月份"),
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    """
    ### 權限要求
    - 需通過 JWT Token 驗證。
    - 僅能查詢該 `user_id` 所屬的資料。

    ### 回傳格式說明 (Success JSON)
    - `total_count`: 該月總筆數
    - `monthly_income`: 總收入
    - `monthly_expenses`: 總支出
    - `monthly_balance`: 結餘 (收入 - 支出)
    - `data`: 包含 `account_name` 與 `currency` 的詳細收支紀錄清單
    """
    # 使用 SQLAlchemy ORM 與資料庫溝通
    # 1. 建立基礎查詢與 LEFT JOIN
    stmt = (
        select(
            AddRecord,
            Account.account_name,
            Account.currency,
        )
        .join(
            Account,
            and_(
                AddRecord.user_id == Account.user_id,
                AddRecord.account_id == Account.account_id,
            ),
            isouter=True,  # 實現 LEFT JOIN
        )
        .filter(AddRecord.user_id == current_user.user_id)
        # 2. 關鍵：使用 extract 函數篩選特定年、月
        .filter(extract("year", AddRecord.add_date) == year)
        .filter(extract("month", AddRecord.add_date) == month)
        # 3. 排序：按日期降序排列
        .order_by(AddRecord.add_date.desc(), AddRecord.add_id.desc())
    )

    # 執行查詢，獲取所有結果行
    results = db.execute(stmt).all()

    # 4. 資料格式化
    formatted_data = []
    monthly_income = Decimal("0.0")  # 順便計算該月總收入
    monthly_expenses = Decimal("0.0")  # 順便計算該月總支出

    for row in results:
        record = row[0]  # AddRecord ORM 物件
        account_name = row[1]  # account_name 字串
        currency = row[2]  # currency 字串

        item = {
            "add_id": record.add_id,
            "add_date": record.add_date,
            "add_amount": record.add_amount,
            "add_type": record.add_type,  # True 為收入, False 為支出
            "add_class": record.add_class,
            "add_class_icon": record.add_class_icon,
            "account_id": record.account_id,
            "add_member": record.add_member,
            "add_tag": record.add_tag,
            "add_note": record.add_note,
            "created_at": record.created_at,
            "currency": currency or "N/A",
            "account_name": account_name or "未分類帳戶",
        }
        formatted_data.append(item)

        # 累計總收入與總支出
        if record.add_type is True:  # 收入
            monthly_income += record.add_amount
        else:  # 支出
            monthly_expenses += record.add_amount

    monthly_balance = monthly_income - monthly_expenses  # 計算月結餘

    # 5. 返回結果
    return {
        "success": True,
        "year": year,
        "month": month,
        "total_count": len(formatted_data),  # 總筆數
        "monthly_income": round(monthly_income, 2),  # 四捨五入到小數兩位
        "monthly_expenses": round(monthly_expenses, 2),
        "monthly_balance": round(monthly_balance, 2),
        "data": formatted_data,
    }


@router.get("/stats/monthly")
async def get_monthly_stats(
    db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)
):
    today = date.today()
    # 本月第一天
    this_month_first = today.replace(day=1)

    # --- 獲取上個月日期範圍 ---
    # 邏輯：本月第一天減去 1 天就是上個月最後一天
    last_month_end = this_month_first - timedelta(days=1)
    last_month_first = last_month_end.replace(day=1)

    # 1. 查詢本月資料 (你原有的邏輯)
    this_expense = db.query(func.sum(AddRecord.add_amount)).filter(
        AddRecord.user_id == current_user.user_id,
        AddRecord.add_type == False,
        AddRecord.add_date >= this_month_first,
    ).scalar() or Decimal("0")
    this_income = db.query(func.sum(AddRecord.add_amount)).filter(
        AddRecord.user_id == current_user.user_id,
        AddRecord.add_type == True,
        AddRecord.add_date >= this_month_first,
    ).scalar() or Decimal("0")

    # 2. 查詢上月資料 (新增)
    last_expense = db.query(func.sum(AddRecord.add_amount)).filter(
        AddRecord.user_id == current_user.user_id,
        AddRecord.add_type == False,
        AddRecord.add_date >= last_month_first,
        AddRecord.add_date <= last_month_end,
    ).scalar() or Decimal("0")
    last_income = db.query(func.sum(AddRecord.add_amount)).filter(
        AddRecord.user_id == current_user.user_id,
        AddRecord.add_type == True,
        AddRecord.add_date >= last_month_first,
        AddRecord.add_date <= last_month_end,
    ).scalar() or Decimal("0")

    # 3. 計算成長率公式: ((本月 - 上月) / 上月) * 100
    def calc_change(this_val, last_val):
        if last_val == 0:
            return 100.0 if this_val > 0 else 0.0
        return round(float((this_val - last_val) / last_val * 100), 1)

    return {
        "month": today.strftime("%Y-%m"),
        "total_expense": float(this_expense),
        "total_income": float(this_income),
        "net_savings": float(this_income - this_expense),
        # 新增回傳欄位給前端 % 使用
        "expense_change": calc_change(this_expense, last_expense),
        "income_change": calc_change(this_income, last_income),
    }


# 3. 新增收支紀錄 API
@router.post("/", response_model=AddRecordResponse)
async def create_record(
    data: AddRecordCreate,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    new_record = AddRecord(user_id=current_user.user_id, **data.dict())
    db.add(new_record)
    db.flush()  # 先取得 ID 但不提交

    success, msg = RecordsService.process_record_logic(db, current_user.user_id, new_record)
    if not success:
        db.rollback()
        raise HTTPException(status_code=400, detail=msg)

    return new_record


# 4. 修改紀錄 API (PATCH)
@router.patch("/{record_id}", response_model=AddRecordResponse)
async def update_record(
    record_id: int,
    data: AddRecordUpdate,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    db_record = db.query(AddRecord).filter(
        AddRecord.add_id == record_id,
        AddRecord.user_id == current_user.user_id
    ).first()
    if not db_record:
        raise HTTPException(status_code=404, detail="找不到該筆紀錄")

    success, msg = RecordsService.update_record_logic(
        db, current_user.user_id, db_record, data.dict(exclude_unset=True)
    )
    if not success:
        db.rollback()
        raise HTTPException(status_code=404, detail=msg)

    return db_record


# 5. 刪除紀錄 API
@router.delete("/{record_id}")
async def delete_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    record = (
        db.query(AddRecord)
        .filter(
            AddRecord.add_id == record_id, AddRecord.user_id == current_user.user_id
        )
        .first()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="紀錄不存在或無權限刪除")

    # 1. 處理帳戶餘額與儲蓄目標還原 (保留你原本的完美邏輯)
    account = db.query(Account).filter(Account.account_id == record.account_id).first()
    if account:
        if record.add_type is False:
            account.current_balance += record.add_amount
        else:
            account.current_balance -= record.add_amount

        # 儲蓄目標同步還原
        # 只有刪除「收入」時，才需要扣除對應儲蓄目標的進度
        goal = db.query(SavingsGoal).filter(
            SavingsGoal.account_id == record.account_id,
            SavingsGoal.user_id == current_user.user_id
        ).first()

        if goal:
            # 扣除進度
            goal.current_amount -= record.add_amount

            # 狀態判定：如果扣除後低於目標，且原本狀態是已完成 (completed)
            if goal.current_amount < goal.target_amount and goal.status == "completed":
                goal.status = "active"  # 改回進行中

    # 🚀 關鍵新增：2. 先刪除關聯的「訂單明細」子項目
    db.query(AddItem).filter(AddItem.add_id == record_id).delete(synchronize_session=False)

    # 3. 再刪除主紀錄
    db.delete(record)
    
    # 4. 最後一次提交所有變更
    db.commit()
    
    return {"msg": "紀錄與明細已成功刪除，帳戶餘額已同步更新"}



#---------add_item表格相關路由
@router.get("/{record_id}/items")
async def get_record_items(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    record = db.query(AddRecord).filter(
        AddRecord.add_id == record_id,
        AddRecord.user_id == current_user.user_id
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="找不到該筆紀錄")

    items = db.query(AddItem).filter(
        AddItem.add_id == record_id
    ).order_by(AddItem.sort_order).all()

    return {"add_id": record_id, "items": items}



# --- 這是你想要的 AI 快速記帳路由 ---

@router.post("/ai-add")
async def ai_create_record(
    files: List[UploadFile] = File(...),  # ← file 改成 files
    account_name: str = Form(default="現金"),
    platform: str = Form(default="foodpanda"),
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    """
    接收截圖 → Gemini解析 → 寫入 adds + add_items
    """

    # 取得歷史分類
    history_classes = db.query(AddRecord.add_class).filter(
        AddRecord.user_id == current_user.user_id
    ).distinct().all()
    history_classes = [c[0] for c in history_classes]


    images_bytes = [await f.read() for f in files]  
    parsed = await GeminiService.parse_receipt_images(images_bytes, platform)
    parsed["add_class"] = "訂單"
    print("🔥 parsed:", parsed)

    if "error" in parsed:
        raise HTTPException(status_code=422, detail=parsed["error"])

    # 3. 補上使用者相關欄位
    parsed["account_name"] = account_name
    parsed.setdefault("add_member", "自己")
    parsed.setdefault("add_tag", "需要")

    items = parsed.pop("items", [])

    parsed["store_name"] = parsed.pop("store", None)

    parsed["order_number"] = (
        parsed.get("order_number") 
        or parsed.pop("order_id", None)
    )

    # 4. 建立主記帳
    try:
        RecordsService.create_add_record(db, current_user.user_id, parsed)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 5. 取得剛建立的紀錄
    new_record = db.query(AddRecord).filter(
        AddRecord.user_id == current_user.user_id
    ).order_by(AddRecord.add_id.desc()).first()

    # 6. 寫入品項明細
    if items and new_record:
        RecordsService.create_add_record_with_items(
            db, current_user.user_id, new_record, items
        )
        db.commit()

    return {
        "success": True,
        "add_id": new_record.add_id if new_record else None,
        "store": parsed.get("store", ""),
        "total_amount": parsed.get("add_amount", 0),
        "items_count": len(items),
        "items": items,
        "msg": f"已為您將訂單拆分為 {len(items)} 筆明細並記帳成功！"
    }
    

# 純解析，不存 DB
@router.post("/ai-parse")
async def ai_parse_receipt(
    files: List[UploadFile] = File(...),  # ← 改成 List
    platform: str = Form(default="foodpanda"),  # ← 加這行
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):

    images_bytes = [await f.read() for f in files]
    parsed = await GeminiService.parse_receipt_images(images_bytes, platform)  

    if "error" in parsed:
        raise HTTPException(status_code=422, detail=parsed["error"])

    return {
        "success": True,
        "data": parsed  # 只回傳解析結果，不碰 DB
    }


# 使用者確認後才存 DB
@router.post("/ai-confirm")
async def ai_confirm_record(
    payload: dict,  # 前端把修改後的資料送過來
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    print("🔍 收到 payload:", payload.get("account_name"))  # ← 加這行確認
    items = payload.pop("items", [])
    payload.setdefault("store_name", payload.pop("store", None))  # ← 把 store 對應到 store_name
    payload.setdefault("order_number", None)

    # ← 改這裡：get 不移除，讓 payload 保留 account_id
    account_id = payload.get("account_id")  # pop 改 get
    if account_id:
        account = db.query(Account).filter(
            Account.account_id == account_id,
            Account.user_id == current_user.user_id
        ).first()
        if account:
            payload["account_name"] = account.account_name
    # account_id 還在 payload 裡，create_add_record 就能用它查帳戶了
    
    try:
        RecordsService.create_add_record(db, current_user.user_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    new_record = db.query(AddRecord).filter(
        AddRecord.user_id == current_user.user_id
    ).order_by(AddRecord.add_id.desc()).first()

    if items and new_record:
        RecordsService.create_add_record_with_items(
            db, current_user.user_id, new_record, items
        )
        db.commit()

    return {
        "success": True,
        "add_id": new_record.add_id if new_record else None,
        "msg": f"記帳成功！共 {len(items)} 項明細"
    }
    
    

@router.get("/orders")
async def get_order_list(
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    """取得有品項明細的訂單列表"""
    query = db.query(AddRecord).filter(
        AddRecord.user_id == current_user.user_id,
        AddRecord.store_name != None  # 只撈有 store_name 的（訂單掃描產生的）
    )
    if search:
        query = query.filter(
            or_(
                AddRecord.store_name.ilike(f"%{search}%"),
                AddRecord.order_number.ilike(f"%{search}%"),
                AddRecord.add_note.ilike(f"%{search}%"),
            )
        )

    total_count = query.count()
    records = (
        query.order_by(AddRecord.add_date.desc(), AddRecord.add_id.desc())
        .limit(page_size).offset((page - 1) * page_size).all()
    )

    result = []
    for record in records:
        items = db.query(AddItem).filter(
            AddItem.add_id == record.add_id
        ).order_by(AddItem.sort_order).all()

        # 取帳戶名
        account = db.query(Account).filter(
            Account.account_id == record.account_id
        ).first()

        result.append({
            "add_id": record.add_id,
            "store_name": record.store_name,
            "order_number": record.order_number,
            "add_date": str(record.add_date),
            "add_amount": float(record.add_amount),
            "add_note": record.add_note,
            "account_name": account.account_name if account else "未知帳戶",
            "items": [
                {
                    "item_name": item.item_name,
                    "item_amount": float(item.item_amount),
                    "item_class": item.item_class,
                    "quantity": item.quantity if hasattr(item, 'quantity') else 1,
                }
                for item in items
            ]
        })

    return {
        "success": True,
        "data": result,
        "pagination": {
            "current_page": page,
            "page_size": page_size,
            "total_rows": total_count,
            "total_pages": math.ceil(total_count / page_size) if total_count > 0 else 1,
        }
    }

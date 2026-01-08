# ORM使用說明
[回首頁](../README.md) |
[實戰範例](../docs/add.md)


## SQLAlchemy (ORM Models)
- 定義位置: web_app/models/models.py
- 主要用途: 對接資料庫。定義資料庫表結構、欄位類型、索引、外鍵。
- 意義: 讓 Python 程式碼能像操作物件一樣操作 SQL。
- 操作對象: Session (db) 資料庫連線。
- 優點: 程式碼直觀、防止 SQL 注入、自動處理 Python Decimal 與資料庫 Numeric 的轉換。
- 適用場景: 新增紀錄、修改餘額、關聯查詢（例如：查詢紀錄時順便取得帳戶名稱）。

```bash
# 範例：取得單筆紀錄
record = db.query(AddRecord).filter(AddRecord.id == record_id).first()
```

## 什麼時候該用 ORM？
- 涉及「資料庫讀寫」時，必須使用 ORM 模型。
- 新增/修改資料： 建立一個新的 ORM 物件並 db.add()。
- 複雜查詢： 使用 query.filter(), func.sum(), or_() 進行過濾。
- 關聯操作： 處理 user_id 與 account_id 之間的外鍵關係。
- ❌ 錯誤示範： 在 Route 裡直接寫 SQL 字串 SELECT * FROM Adds WHERE... (這會失去 ORM 的類型安全與安全性)。

- 參考:

```bash
from fastapi import Depends
from sqlalchemy.orm import Session
from web_app.database import get_db
from web_app.models.member import Member

@router.get("/members")
def get_members(db: Session = Depends(get_db)):
    return db.query(Member).all()

```

```bash
    """
    取得通訊錄列表（使用 ORM）

    支援功能：
    - 分頁：page, page_size
    - 搜尋：search（搜尋 name, email, mobile, address）
    - 排序：sort_by（ab_id 或 birthday），sort_order（asc 或 desc）

    Args:
        page: 頁碼（從 1 開始）
        page_size: 每頁筆數（1-100）
        search: 搜尋關鍵字
        sort_by: 排序欄位（ab_id 或 birthday）
        sort_order: 排序方向（asc 或 desc）
        db: 資料庫 session

    Returns:
        {
            "success": True,
            "data": [...],
            "pagination": {...},
            "filters": {...}
        }
    """

```

```bash
   try:
        # 驗證排序欄位
        allowed_sort_fields = ["ab_id", "birthday"]
        if sort_by and sort_by not in allowed_sort_fields:
            raise HTTPException(
                status_code=400,
                detail=f"不支援的排序欄位。允許的欄位: {', '.join(allowed_sort_fields)}",
            )

        # 驗證排序方向
        sort_order = sort_order.lower()
        if sort_order not in ["asc", "desc"]:
            raise HTTPException(
                status_code=400, detail="排序方向只能是 asc 或 desc"
            )

        # 驗證分頁參數
        if page < 1:
            raise HTTPException(status_code=400, detail="頁碼必須大於 0")
        if page_size < 1 or page_size > 100:
            raise HTTPException(
                status_code=400, detail="每頁筆數必須介於 1 到 100 之間"
            )

        # 建立基礎查詢
        query = db.query(AddressBook)

        # 搜尋條件
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    AddressBook.name.like(search_pattern),
                    AddressBook.email.like(search_pattern),
                    AddressBook.mobile.like(search_pattern),
                    AddressBook.address.like(search_pattern),
                )
            )

        # 計算總筆數
        total_rows = query.count()

        # 排序
        if sort_by:
            sort_column = getattr(AddressBook, sort_by)
            if sort_order == "asc":
                query = query.order_by(sort_column.asc())
            else:
                query = query.order_by(sort_column.desc())
        else:
            # 預設排序
            query = query.order_by(AddressBook.ab_id.desc())

        # 分頁
        offset = (page - 1) * page_size
        items = query.offset(offset).limit(page_size).all()

        # 計算總頁數
        total_pages = ceil(total_rows / page_size)

        # 將 ORM 物件轉換為字典列表
        data = [
            {
                "ab_id": item.ab_id,
                "name": item.name,
                "avatar": item.avatar,
                "email": item.email,
                "mobile": item.mobile,
                "birthday": (
                    item.birthday.isoformat() if item.birthday else None
                ),
                "address": item.address,
                "created_at": item.created_at.isoformat(),
            }
            for item in items
        ]

        return {
            "success": True,
            "data": data,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_rows": total_rows,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
            "filters": {
                "search": search,
                "sort_by": sort_by,
                "sort_order": sort_order,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"資料庫錯誤: {str(e)}")

```
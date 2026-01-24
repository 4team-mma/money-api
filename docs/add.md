# 實戰範例：以 AddRecord 為例
[回首頁](../README.md) |
[ORM](../docs/orm.md) |
[Pydanic](../docs/pydanic.md) 

## 開發建議
- 標準 CRUD (Pydantic 驗證 + ORM 寫入)
- 適用於： register (註冊), update_member_profile (更新個人資料), create_record (新增帳單)。
- 分頁與統計 (ORM 查詢 + Pydantic 回傳)
- 適用於： get_records (歷史帳單清單), get_admin_rankings (後台排行榜)。
- 新增/修改 (Post/Patch)：一律先寫 Schema (Pydantic) 定義規則，再由 Route 轉交 ORM (Model) 寫入。
- 讀取/列表 (Get)：優先使用 ORM 進行 filter 與 join；若需要排行榜等統計，利用 sqlalchemy.func 在資料庫端計算，嚴禁在 Python 裡用 for 迴圈算錢。
- 安全性：所有的查詢回傳必須檢查是否包含敏感欄位。利用 response_model 來過濾密碼與私密資訊。
- 檔案處理：僅在處理圖片或附件時改用 Form 格式，其餘 API 統一使用 JSON。


## 定義資料 (兩者都要寫)
- ORM (models.py): 定義 AddRecord 類別，繼承 Base。
- Pydantic (schemas/add.py): 定義 AddRecordCreate (用來接資料) 與 AddRecordResponse (用來回傳)。
- 「資料庫操作層 (ORM vs SQL)」與「資料交換層 (Pydantic)」



## 在 Route 中協作

```bash
@router.post("/", response_model=AddRecordResponse) # <--- 指定輸出用 Pydantic 格式
async def create_record(
    data: AddRecordCreate,   # <--- 1. 使用 Pydantic 驗證進入的資料
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    # 2. 業務邏輯處理 (例如 Decimal 轉換)
    amt_decimal = Decimal(str(data.add_amount))

    # 3. 將 Pydantic 轉換為 ORM 模型，準備寫入資料庫
    new_record = AddRecord(
        user_id=user_id,
        **data.dict()  # 將 Pydantic 模型轉為字典，解構成 ORM 欄位
    )

    db.add(new_record) # 4. 使用 ORM 存檔
    db.commit()
    db.refresh(new_record)
    
    return new_record # 5. 雖然回傳 ORM 物件，但 FastAPI 會根據 response_model 自動轉成 Pydantic JSON

```

## 團隊統一規則 (Best Practices)
- 禁寫 Raw SQL： 除非 ORM 完全無法實現的極複雜效能優化，否則一律使用 db.query(Model)。
- Schema 命名規範：
- Create: 用於 POST (欄位較全，包含必填項)。
- Update: 用於 PATCH (所有欄位皆設為 Optional，只更新有傳的)。
- Response: 用於輸出 (可格式化日期、排除敏感欄位)。
- ORM 物件不在前端直接呈現： 永遠透過 response_model 過濾 ORM 物件。這能防止資料庫異動導致前端 API 報錯。
- 計算與統計： 像「本月收支統計」這種功能，使用 ORM 的 func.sum() 是最佳實作，因為它在資料庫層級計算，效能最高。



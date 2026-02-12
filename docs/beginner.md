# 📘 MoneyMMA 後端 API 文件撰寫規範 (SOP)
[回首頁](../README.md)

## 新手指南
api裡面有需多名詞不太理解，會記錄在這邊供參考。

## Depends
1.Depends會確保`get_current_user` 存在。
2.有些會使用`uid = current_user.user_id` 就不用寫這麼長。
```bash
        #意思相同
        Checkin.user_id == current_user.user_id, 
        Checkin.user_id == uid, # 不過這個前面要先定義uid = current_user.user_id
```
**比較**:`dependencies`和 `Depends` 差異。
- `from dependencies import get_current_user`: 這只是把「函式」引進來，還沒執行。
- `Depends(get_current_user)`: 這是在告訴 FastAPI：「在執行這個路由之前，請先幫我跑一遍 `get_current_user` 函式，並把它回傳的結果（User 物件）塞給我。」

## from ...import 引用檔案
有兩種方法，一種往前推的相對路徑`..`(1個點是當前目錄,2個是上層,3個是再上層..)或者用絕對路徑。
**推薦的寫法 (絕對路徑)**:用「專案根目錄」為起點的寫法（假設你的根資料夾叫 web_app）：
```bash
# 例如routes的引用:
from web_app.dependencies import get_current_user


# 例如schemas的引用:
# 絕對路徑引用 (推薦，清楚明瞭)
from schemas.gamification import checkin as schemas

# 相對路徑引用 (方便，但層級多了容易亂)
from ..schemas.accounts import AccountCreate
```

## `response_model`的寫法:
寫法 A 適合內部開發快速迭代，寫法 B 適合正式專案。
```bash
# 寫法 A (簡潔)
@router.post("/action", response_model=schemas.CheckinResponse)

# 寫法 B (詳細文件)
@router.get("/", response_model=List[AccountResponse], summary="...", description="...")
```

## db.query()說明:
### 1.db.query().filter比對:
**圖解：物件 vs ID 的差異**(想像你拿著「身分證(ID)」給警衛看，警衛是對照上面的「號碼」，而不是把整個人塞進機器裡比對。)
- `db.query().filter(xxx.user_id == current_user.user_id)`要這種寫法才對。
你必須把物件裡的 ID 「取出來」 變成數字，才能跟資料庫欄位比對。
- **錯誤寫法**:
`db.query(Checkin).filter(Checkin.user_id == current_user)`，
因為那是資料庫SQLAlchemy對應的欄位user_id是要int但你卻給他物件，會報錯混淆。
### 2.db.query()的使用:
- 當使用`db: Session = Depends(get_db)`是因為要使用`db.query`，如果不用其實就不用寫。
- **用途：**`db` 這個變數是用來執行資料庫操作的，例如：
1.查詢：db.query(...)
2.新增：db.add(...)
3.存檔：db.commit()
4.更新：db.refresh(...)
- **結論：**如果你的路由函式（Route Function）裡面 完全沒有用到 上述任何一個指令，你就可以把它拿掉。
```bash
# 通常都會有user
# 當user被當成物件時(我們是用這種寫法):
def get_dashboard_summary(current_user: Member=Depend(get_current_user), db: Session = Depends(get_db)): 

# 當user不是物件:
def get_dashboard_summary(user_id: int, db: Session = Depends(get_db)):

# 當只回傳current_user，不需要查看資料庫，所以拿掉 db:
@router.get("/info", response_model=schemas.GameSummary)
def get_game_summary(current_user: Member = Depends(get_current_user)):
    return current_user

```

## Return 的寫法：什麼時候可以偷懶？
這取決於你的 Response Schema (Pydantic) 有多聰明。
### 情況 A：可以偷懶 (直接 return 物件)
當你的 資料庫模型 (Model) 和 回傳模型 (Schema) 的欄位名稱一模一樣時。
- DB Model (`Checkin`) 有：`streak_count`, `total_checkins`, `earned_xp`
- Schema (`CheckinResponse`) 有：`streak_count`, `total_checkins`, `earned_xp`
這時候你直接 `return new_checkin` (資料庫物件)，FastAPI 會啟動 **「ORM 模式」**，自動幫你把物件裡的屬性抓出來填進 Schema。
### 情況 B：必須手寫 (return dict)
當你的 Schema 裡面有一些欄位，是 資料庫裡沒有的，或者是需要 即時計算 的。會隨時間改變的變數。
- Schema (`CheckinStatus`) 需要：`has_checked_in` (布林值)
- DB Model：根本沒有 `has_checked_in` 這個欄位！(我們是靠 query 查出來有沒有紀錄，而不是存一個欄位)
```bash
return {
    "has_checked_in": True, # 這是算出來的
    "streak": 5,
    "today_xp_reward": 10
}
```

## 在schemas中的class Config: from_attributes = True 是什麼？:
這是 Pydantic V2 (FastAPI 用的驗證庫) 的一個魔法設定（在舊版 V1 叫做 `orm_mode = True`）。

- **沒有這行時：**:Pydantic 只讀得懂字典 (dict)，例如 `{"`user_id": 1, "xp": 100}`。
你必須把物件裡的 ID 「取出來」 變成數字，才能跟資料庫欄位比對。
- **加了這行後：**:
Pydantic 變得看得懂 **SQLAlchemy** 物件 了！它可以直接讀取 `user`.`user_id` 或 `user.xp` 這種屬性寫法。
**為什麼要加？**因為我們從資料庫拿出來的是 SQLAlchemy 物件 (`new_checkin`)，如果沒加這行，你必須自己手動把它轉成字典才能回傳，非常麻煩。加了這行，就可以直接 `return new_checkin`，FastAPI 會自動幫你轉。


## 什麼時候要使用是什麼`@router.get("/")`？:
- `@router.get("/")` (列表)：通常是用來**列出所有歷史紀錄**，例如使用者想看「我上個月哪幾天有打卡」。目前你的前端需求似乎只需要知道「今天打卡沒？」跟「連續幾天？」，所以暫時用不到。
- `@router.get("/status")` (狀態)：這才是你現在需要的。它告訴前端「當下的狀態」，讓前端決定顯示什麼畫面。
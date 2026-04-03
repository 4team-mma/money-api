# 📘 MoneyMMA 後端 API 文件撰寫規範 (SOP)
[回首頁](../README.md)

### 適用版本: FastAPI + Pydantic V2 | 最後更新: 2026-02-01

為了確保團隊開發的 API 文件 (Swagger UI) 統一、美觀且具備高可讀性，所有開發人員請務必遵守以下 **三步驟撰寫流程**。

---

## 🚀 核心觀念：要寫在哪裡？ (Field vs Query)

在寫文件前，請先判斷你的參數性質：

| 判斷標準 | 使用工具 | 撰寫位置 | 適用場景 | 資安等級 |
| :--- | :--- | :--- | :--- | :--- |
| **敏感資料 / 複雜結構** | `Pydantic Field` | **Schemas (`schemas/*.py`)** | POST/PUT Body (登入、註冊) | 🔒 高 |
| **公開篩選 / 簡單參數** | `FastAPI Query` | **Router (`routes/*.py`)** | GET URL 參數 (搜尋、分頁) | 🔓 低 |

---

## 步驟 1：設定 API 標題 (Summary)
- **位置**：Router 檔案 (`routes/xxx.py`)
- **規範**：請加上 Emoji Icon，並使用簡短的動詞。

```bash
```python
# ✅ 正確範例
@router.post("/auth/login", summary="🔐 會員登入")
async def login(...):
    pass
```

## 步驟 2：撰寫詳細說明 (Docstring)
- **位置**：函式下方的 `""" """` 區塊。
- **規範**：支援 Markdown 語法，請說明邏輯、限制與錯誤代碼。
```bash
```python
# ✅ 正確範例
@router.post("/auth/login", summary="🔐 會員登入")
async def login(...):
    """
    (這裡寫詳細說明)
    一般會員登入接口，取得 JWT Token。

    - **輸入限制**:
        - `identifier`: 支援 Email 或 Username。
        - `password`: 密碼錯誤統一回傳 401。

    - **回傳**: JWT Access Token。
    """
    # ... 程式碼邏輯
```
## 步驟 3：定義參數範例 (Examples)
這一步最關鍵，決定了前端按 "Try it out" 時會自動帶入什麼值。
### 🅰️ 情況 A：POST/PUT Body (去 Schemas 寫)
- **位置**：適用：Pydantic V2
- **位置**： `schemas/xxx.py` 你想找路由對應的schemas可以看上面的`from ..schemas.`看是在哪裡。
- **規範**：使用 `Field` 搭配 `examples` (注意是複數)。

```bash
from pydantic import BaseModel, Field

class MemberLogin(BaseModel):
    # ✅ 正確範例
    identifier: str = Field(
        ...,
        description="使用者帳號或信箱",
        examples=["user@example.com"]  # 🌟 這裡會變成 Swagger 的預設填入值
    )

    password: str = Field(
        ...,
        description="使用者密碼",
        examples=["mypassword123"]
    )
```
### 🅱️ 情況 B：GET Query (在 Router 寫)
- **位置**：網址參數 (如 `/report?year=2026`)
- **位置**： `routes/xxx.py`
- **規範**：使用 `Query` 搭配 `examples`。
```bash
from fastapi import Query

@router.get("/report", summary="📊 匯出報表")
async def export_report(
    # ✅ 正確範例
    time_range: str = Query(
        "current-month",
        description="時間範圍代碼",
        examples=["year-2026"] # 🌟 Swagger 範例
    )
):
    pass
```

## ✅ 成果檢核 (Checklist)
完成後打開 `/docs` 確認：
- **[]標題**：API 旁邊是否有綠色/藍色的 Emoji 標題？ (步驟 1)
- **[]說明**：展開後是否有詳細的文字說明？ (步驟 2)
- **[]測試**：按下 Try it out 後，輸入框是否自動填入了範例值？ (步驟 3)

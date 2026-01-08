# Pydanic使用說明
[回首頁](../README.md) |
[實戰範例](../docs/add.md)

## Pydantic (Schemas)
- 定義位置: web_app/schemas/*.py
- 主要用途: 對接前端 (API)。資料驗證、過濾、類型轉換 (Serialization)。
- 意義: 確保前端傳來的資料是正確的，並過濾敏感資訊。
- 操作對象: Request / Response 資料交換。
- 不論資料庫是用 ORM 還是 SQL 讀取，API 的進入與輸出都必須經過 Pydantic。
- 前端傳送 JSON 或 Form Data 時，Pydantic 負責第一線「擋掉爛資料」，檢查金額是否為正數、日期格式是否正確。
- 範例：
```bash
# 就算前端傳字串 "100.5"，Pydantic 也會自動幫你轉成 Decimal
class AddRecordCreate(BaseModel):
    add_amount: Decimal 
    add_date: date
```

## 什麼時候該用 Pydantic？
- 當資料進出 API 時，必須使用 Pydantic Schemas。
- Request Validation (進)： 前端傳來的內容（例如：AddRecordCreate），確保金額是數字、日期格式正確。
- Response Modeling (出)： 定義 AddRecordResponse。它可以隱藏敏感欄位（如密碼 password），只吐出前端需要的資料。

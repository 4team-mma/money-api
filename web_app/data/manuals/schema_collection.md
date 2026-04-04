# 🐈 MoneyAI 財務系統資料庫架構說明書 (Schema Collection)

## 核心規則 (Global Rules)
- **user_id 隔離**: 所有的查詢必須包含 `WHERE user_id = {user_id}`。
- **日期處理**: 預設使用 `add_date` 進行時間範圍過濾。
- **模糊搜尋**: 針對備註或名稱，務必使用 `LIKE '%關鍵字%'`。

---

## 1. members (會員中心)
- `user_id`: 主鍵，使用者唯一識別碼。
- `xp`, `level`, `points`: 遊戲化數值。
- `job`: 使用者職業，可用於財務建議背景。

## 2. accounts (帳戶管理)
- `account_id`: 主鍵。
- `account_name`: 帳戶名稱（如：我的錢包、中信卡）。
- `current_balance`: 目前餘額。
- `account_type`: 帳戶類型。

## 3. adds (核心收支表 - 最常用)
- `add_id`: 主鍵。
- `add_type`: **核心欄位**。0 = 支出 (Spending), 1 = 收入 (Income)。
- `add_amount`: 金額。支出通常顯示正數，計算總額時要注意。
- `add_class`: 分類名稱（如：飲食、交通、購物）。
- `add_note`: **關鍵字查詢目標**。具體品名（如：橘子、牛肉麵、公車費）存於此欄位。
- `add_tag`: 標籤。

## 4. transactions (轉帳紀錄)
- `from_account_id`: 轉出帳戶。
- `to_account_id`: 轉入帳戶。
- `amount`: 轉帳金額。

## 5. notifications (提醒與行事曆)
- `reminder_title`: 提醒內容。
- `reminder_date_start`: 提醒日期。
- `repeat_cycle`: 週期 (none, daily, weekly, monthly)。

## 6. budgets (預算設定)
- `amount`: 預算限額。
- `category`: 該預算所屬分類，若為空則代表月總預算。

## 7. cpi_data (物價指數)
- `category`: 商品類別（如：食物類、燃料費）。
- `val`: CPI 數值或年增率。

## 8. salary_benchmarks (薪資水準)
- `industry`: 行業名稱。
- `salary_val`: 平均薪資金額。

## 9. settings (系統偏好)
- `budget_cycle`: 預算週期 (monthly, weekly)。
- `app_theme`: 介面主題。

## 10. ai_configs (AI 配置)
- 儲存使用者自訂的 AI 提供商與 Key。

## 11. checkin (打卡紀錄)
- `streak_count`: 連續打卡天數。

## 12. misscards_library (卡牌與成就倉庫)
- 存放所有任務、卡牌與成就的靜態定義。

## 13. daily_missions (每日隨機任務)
- `miss_status`: 0=進行中, 1=待領取, 2=已領取。

## 14. ach_cards (用戶持有圖鑑)
- 使用者已解鎖的卡牌或成就。

## 15. savings_goals (儲蓄目標)
- `target_amount`: 目標金額。
- `current_amount`: 已儲蓄金額。

## 16. login_activities (登入活動)
- 紀錄登入 IP、設備與位置。

## 17. intent_review_log (意圖審核日誌)
- 紀錄 AI 判斷與人類修正的歷史，用於優化大腦。

## 18. password_resets (密碼重設)
- 紀錄 OTP 驗證碼與過期時間。
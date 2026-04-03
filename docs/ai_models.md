# 🐈 AI 模型設定與開發指南

[回首頁](../README.md)

---

## 🏠 本地端設置 (安裝與執行)

### 1. Ollama (地端首選)
- **官方網站**：[Ollama.com](https://ollama.com/)
- **預設模型**：`gemma3:1b` (Google 最新輕量開源模型)
  - **優點**：極致輕量，舊款 Mac 與文書型 Windows 筆電可嘗試使用但有點免強。
  - **進階選項**：若設備有獨立顯卡 (GPU)，可等系統更新 `llama3.2` 或 `deepseek-r1:7b` 獲得更強的邏輯推理能力。
- **Host 位址**：`http://localhost:11434`
- **連線架構**：
  - 後端使用 `httpx` (非同步) 發送請求。
  - 透過 `OllamaService` 封裝標準化接口，讓地端模型也能讀取複雜的財務上下文。

### 2. AnythingLLM (輔助方案)
- **定位**：為了舊款 MacOS筆電能連地端，管理者W表示使用但有點卡頓，容易發燙，偶爾能成功，參考資料請往下看。
- **舊款規格**：MacBook Pro(macOS 13.6.3) /13-inch, 2017, 記憶體 8 GB 2133MHz LPDDR3
- **連線方式**：透過本地 API Server (`http://localhost:3001`) 整合。
- **安全驗證**：請求 Header 需注入 `Authorization: Bearer {API_KEY}`。
該模型本身就是一套已經寫好 RAG（檢索增強生成）機制的完整系統，所以你的 Router 只需要用 httpx 把問題 POST 給它的 Workspace 就好，所以不需要像Gemini跟Ollima需要另寫一個Service.py
---

## ☁️ 雲端 API 設置: Google Gemini

### 1. 模型版本策略
系統目前整合了 Google 最新的模型矩陣，並針對不同用途進行了分流：
目前可用:
| 模型名稱 | 代號 (`model_version`) | 特性與用途 | 每日配額 (RPD) |
| :--- | :--- | :--- | :--- |
| **Gemini 2.5 Flash** | `gemini-2.5-flash` | **(預設)** 速度快、額度高，適合開發測試與日常閒聊。 | 每分請求5RPM/每日請求20RPD |

| **Gemini 2.0 Flash** | `gemini-3 flash` | 最新一代模型，反應速度與準確度更佳 (實驗性)。 | 每分請求5RPM/每日請求20RPD |

> **Gemini官方模型:**：
Gemini 2.5 Flash
Gemini 3 Flash/
Gemini 2.5 Flash Lite/
Gemini 2.5 Flash TTS/
Gemini Robotics ER 1.5 Preview/
Gemma 3 12B/
Gemma 3 1B/
Gemma 3 27B/
Gemma 3 2B/
Gemma 34B/
Gemini Embedding 1/
Gemini 2.5 Flash Native Audio Dialog/
[-前往連結-](https://aistudio.google.com/app/usage?timeRange=last-28-days&tab=rate-limit&project=gen-lang-client-0691673939)

### 2. 連線技術細節
- **SDK**：使用官方 `google-genai` 非同步套件。
- **參數調優**：
  - `temperature`: 設定為 `0.15` (低隨機性)，確保 AI 在處理金額與數據時精確不胡說。
  - `top_p`: 設定為 `0.15`，收斂回答範圍。

---

## 🧠 核心架構：智慧財務數據中心 (Finance Data Center)

負責處理「AI 不知道使用者真實財務狀況」的情景。採用 **意圖識別 + 工具函式庫** 的輕量化 RAG 架構。

### 1. 意圖識別大腦 (`FinanceAgentService`)
系統不會無腦地把所有資料塞給 AI (浪費 Token)，而是先分析使用者的問題：
- **問資產** ➔ 自動呼叫 `get_account_summary` (撈取銀行/錢包餘額)。
- **問收支** ➔ 自動呼叫 `get_monthly_stats` 與 `get_recent_transactions` (抓取記帳紀錄)。
- **問物價** ➔ 自動呼叫 `get_cpi_insight` (比對政府 CPI 資料)。
- **問提醒** ➔ 自動呼叫 `get_upcoming_reminders` (查詢行事曆)。

### 2. 財務工具箱 (`FinanceTools`)
封裝了複雜的 SQL 聚合查詢 (Aggregation)，將資料庫的原始數據轉換為 AI 讀得懂的自然語言報告：
- **收支分析**：自動計算類別佔比 (例如：食物類佔 40%)。
- **資產總覽**：自動過濾掉不計入資產的項目 (如信用卡費)，計算準確淨資產。
- **防呆機制**：若查無資料，會回傳明確的「無紀錄」訊息，防止 AI 編造數據。

---

## 🛡️ 安全機制與狀態管理

### 1. 金鑰安全 (Security)
- **AES 加密**：所有 API Key 在寫入資料庫前皆經過加密處理。
- **前端遮蔽**：API 傳回前端時會進行脫敏處理，介面僅顯示 `🔒 系統已安全載入`。

### 2. 狀態持久化 (Persistence)
- **Pinia Store**：集中管理模型設定 (`useAiAdminStore`)，解決切換頁面時設定跑掉的問題。
- **瀏覽器記憶**：對話紀錄存於 `localStorage`，重新整理網頁後，喵喵依然記得剛才聊過什麼。

---

## 🐱 喵喵助手性格封印 (Prompt Engineering)

為了提供既專業又療癒的使用者體驗，我們設計了嚴格的 System Prompt：

### 1. 行為準則
- **極簡模式**：回答限制在 30 字內，直球對決，不說廢話，不過受限官方Gemini模型設置，還是可能超過。
- **角色設定**：自稱「喵喵」，句尾必定帶「喵~」，嚴禁使用簡體字。
- **事實鎖定**：嚴格遵守 `[真實財務資料]` 的內容，若資料庫沒紀錄，必須回答「找不到資料」，**絕對禁止幻覺 (Hallucination) 產生假帳**。

### 2. 隨機互動機制
- 在等待 AI 運算時，前端會隨機播放「喵喵正在翻閱帳本...」、「正在計算罐罐匯率...」等趣味訊息，降低使用者的等待焦慮感。

---

## ❌ 常見問題排除 (Troubleshooting)

| 錯誤代碼 | 狀況說明 | 解決方法 |
| :--- | :--- | :--- |
| **401 Unauthorized** | 身分驗證失效 | 通常發生在後端重啟後。請**登出系統**並清除瀏覽器快取，重新登入即可取得新 Token。 |
| **404 Not Found** | 模型版本錯誤 | 前往「模型管理」頁面，重新選擇模型並點擊「儲存變更」，讓資料庫同步最新設定。 |
| **429 Resource Exhausted** | API 配額用完 | 您觸發了 Google 免費版的速率限制。請休息 60 秒後再試 |
| **下拉選單空白** | 資料庫與前端不一致 | 系統已實作自動修復邏輯，只要重新整理網頁或重新儲存一次設定即可恢復。 |

---

> **開發者筆記**：若要新增新的財務分析功能，請優先在 `FinanceTools` 中擴充 SQL 查詢邏輯，再於 `FinanceAgentService` 中註冊新的關鍵字，即可讓喵喵學會新技能！

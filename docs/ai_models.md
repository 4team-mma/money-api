# 🤖 AI 模型設定與開發指南

[回首頁](../README.md)

---

## 🏠 本地端設置 (安裝與執行)

### 1. Ollama
- **官方網站**：[Ollama.com](https://ollama.com/)
- **預設模型**：`gemma3:1b`
  - **優點**：極輕量，適用於舊款 Mac 與一般 Windows 辦公筆電。
  - **建議**：若設備性能較佳，可嘗試 `llama3.2` 或 `deepseek-r1:7b` 以獲得更精準的分析結果。
- **Host位址**：`http://localhost:11434`
- **注意**：確保 Ollama App 已在後台執行，否則系統會回報「連線失敗」
- **連線方式** : 透過 `httpx` (非同步 HTTP 客戶端) 發送 JSON 請求至 http://localhost:11434/api/chat。

200 原理：只要本地 Ollama 服務有啟動，它就會像一個小型的網頁伺服器，接收我們的問題並回傳答案。

### 2. AnythingLLM (預設為 :舊款Mac可嘗試的地端模型)
- **支援模式**：透過本地端 API 伺服器整合（預設位址 `http://localhost:3001`）。
- **金鑰機制**：需於後台輸入 Workspace API Key。
- **連線方式** : 同樣透過 HTTP 請求，但額外在 Header 注入了 `Authorization: Bearer {API_KEY}` 進行身分驗證。
- **連線保護**：內建 `Retry-After` 邏輯，當遇到 Google 伺服器繁忙 (503) 或流量管制 (429) 時，會自動引導使用者稍後再試，避免程式報錯崩潰。
200 原理：透過 API Key 通過 AnythingLLM 的安全檢查，並由其後端轉發請求給指定的 Workspace 模型。

---

## ☁️ 雲端 API 設置: Gemini (官方 Python SDK)

### 1. Gemini AI 模型 
1. **申請方式**：目前為管理者專用，一般使用者需向管理員申請金鑰。
2. **穩定性優化**：系統已內建「別名轉向邏輯」，自動將 `gemini-1.5-flash` 對齊至 `gemini-flash-latest`，解決 Google API 的 404 報錯問題。
3. **版本選擇**：
   - `Gemini 2.0 Flash`：反應最快，理解力強（推薦）。
   - `Gemini Flash Latest`：最穩定的最新版本。
- **連線方式**：使用 Google 官方提供的 `google-genai` 程式庫。
200 原理：SDK 會自動處理與 `generativelanguage.googleapis.com` 的加密連線、模型別名轉向 (Aliasing) 與內容封裝。



---

## 🛡️ 技術架構與安全機制

### 1. 金鑰鎖定機制 (Security Lock)
- **加密儲存**：金鑰在資料庫中以 AES 規格加密。
- **UI 鎖定**：系統會自動偵測資料庫狀態。若已有 Key，介面會顯示 `🔒 系統已安全載入` 並鎖定輸入框，防止誤觸修改。
- **更新方式**：需手動點擊「修改」按鈕方可解鎖編輯。

### 2. 狀態持久化 (Persistence)
- **Pinia 暫存**：使用 `useAiAdminStore` 集中管理所有模型的配置狀態，解決換頁失憶問題。
- **對話記憶**：喵喵小助手的聊天紀錄存於 `localStorage`，確保頁面跳轉時對話不會消失。

---

## 🐱 喵喵助手性格封印 (Prompting)

為了維持良好的使用者體驗，喵喵的行為受到以下指令約束：

### 1. 智慧字數封印
- **極簡模式**：一般對話限制在 **2-20 中文字** 內，嚴禁發送 Markdown 表格與 LaTeX 公式。
- **分析模式**：當訊息包含 **「分析」** 關鍵字時，喵喵會解鎖封印，提供詳細的數據報告與表格。

### 2. 精準數據抓取
- 測試中...。

---

## ❌ 常見問題與排除 (Troubleshooting)

| 錯誤代碼 | 狀況說明 | 解決方法 |
| :--- | :--- | :--- |
| **404 Not Found** | 模型代號無效 | 系統已內建轉向邏輯，請確保模型版本選對即可。 |
| **429 Resource Exhausted** | API 配額用完 | 喵喵累了，請等 60 秒再重新對話。 |
| **503 Unavailable** | Google 伺服器繁忙 | 這是暫時性塞車，請等 5-10 秒再問一次喵。 |
| **Empty Config** | 切換模型時內容空白 | 點擊左側模型選單，系統會自動從資料庫重新同步。 |

---

> **開發者提醒**：修改後端 `GeminiService` 時，務必將 `temperature` 設為 `0.1`，否則喵喵會控制不住廢話的慾望喵！ 🐾
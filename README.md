#遷移專案說明:API 專案 (money-api)：必須重新 Clone
因為專案歷史紀錄已重整以抹除敏感資訊，請務必執行以下動作：
步驟 A：直接刪除您電腦中原本舊的 money-api 資料夾。原本的.env先複製內容下來，等下新clone的.env內容直接換成這個就好。
步驟 B：重新執行 Clone：
git clone https://github.com/4team-mma/money-api.git

步驟 C  Clone 專案 並進入資料夾。
--------------------------------------------------------------------
複製環境變數env.example 改成 .env (並填入自己的資料庫資訊)。(直接貼上你剛複製的.env程式碼)

安裝依賴：uv sync 

macOS電腦如果執行./dev.sh不允許
請先使用：chmod +x dev.sh
-------------------------------------------------------------------------
開發 API：請去 routes/ 找對應自己的檔案，不要動 models.py，請在裡面實現 CRUD 功能。

測試：打開 http://127.0.0.1:8000/docs 確認 API 能動。

API 測試：請確保在 /docs 測試成功後再進行 git commit。

<h1 align="center">
  mma-app
  <br>
</h1> 

[團隊開發流程](docs/git-workflow.md) |
[專案結構說明](docs/architecture.md) |
[執行流程](docs/dependencies.md) |


## 核心框架
![FastAPI](https://img.shields.io/badge/FastAPI-0.127.0-05998b?logo=fastapi&logoColor=white)
高效能的 Python Web 框架，基於標準 Python 型別提示，內建 Swagger 互動式 API 文件。

## 資料庫與 ORM
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0.45-d71f00?logo=sqlalchemy&logoColor=white)
Python SQL 工具包與物件關係映射 (ORM) 工具，提供靈活且強大的資料庫操作。

![PyMySQL](https://img.shields.io/badge/PyMySQL-1.1.2-4479a1?logo=mysql&logoColor=white)
MySQL 的 Python 驅動程式，用於實現後端與 MySQL 資料庫的實際連線。

## 安全與驗證
![python-jose](https://img.shields.io/badge/python--jose-3.5.0-000000?logo=jsonwebtokens&logoColor=white)
用於處理 JSON Web Tokens (JWT) 的加密、解密與簽章，確保 API 傳輸安全性。

![Bcrypt](https://img.shields.io/badge/Bcrypt-5.0.0-3776ab?logo=python&logoColor=white)
強大的密碼雜湊演算法，用於使用者密碼的加密儲存，防止明文洩漏。

## 開發與測試工具
![Ruff](https://img.shields.io/badge/Ruff-0.14.10-d7ff64?logo=ruff&logoColor=black)
極速的 Python 程式碼檢查 (Linter) 與格式化工具，旨在取代 Flake8 與 Isort。

![pytest-asyncio](https://img.shields.io/badge/pytest--asyncio-1.3.0-0A9EDC?logo=pytest&logoColor=white)
Pytest 的擴充套件，專門用於處理 FastAPI 等非同步 (Async) 程式碼的測試。

![Black](https://img.shields.io/badge/Black-25.12.0-000000?logo=python&logoColor=white)
程式碼格式化工具，確保專案代碼風格高度統一。

# 遷移專案說明:API 專案 (money-api)：必須重新 Clone
因為專案歷史紀錄已重整以抹除敏感資訊，請務必執行以下動作：
- 步驟 A：直接刪除您電腦中原本舊的 money-api 資料夾。原本的.env先複製內容下來，等下新clone的.env內容直接換成這個就好。
- 步驟 B：重新執行 Clone：
git clone https://github.com/4team-mma/money-api.git

- 步驟 C  Clone 專案 並進入資料夾。
## 啟動與安裝依賴流程
- 複製環境變數env.example 改成 .env (並填入自己的資料庫資訊)。(直接貼上你剛複製的.env程式碼)

- 安裝依賴：uv sync 
- macOS電腦如果執行./dev.sh不允許  請先使用：chmod +x dev.sh
--------------------------------------------------------------------
上傳github:
- 請記得先在github開自己的分支
- 然後 先執行 dev.bat 或 dev.sh 看網頁是否能正常連接
- 重新建立git環境: git init
- 查看分支: git branch
- 切換到自己的分支: git switch xxx
- 加入所有檔案: git add .
- 提交註解: git commit -m "註解請說明更新了什麼" 
- 推送到github: git push -u origin xxx
- 到github專案頁面: 此時會跳出推送申請通知pull request
- 核准後，切回到main主支，pull應該就能看到了。
-------------------------------------------------------------------------
開發內容:
- 開發 API：請去 routes/ 找對應自己的檔案，不要動 models.py，請在裡面實現 CRUD 功能。
- 測試：打開 http://127.0.0.1:8000/docs 確認 API 能動。
- API 測試：請確保在 /docs 測試成功後再進行 git commit。

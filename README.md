<h1 align="center">

  mma-app
<img src="./web_app/static/favicon.ico" alt="mma-app" width="30">
</h1> 

[團隊開發流程](docs/git-workflow.md) |
[專案結構說明](docs/architecture.md) |
[執行流程](docs/dependencies.md) |
[ORM](docs/orm.md) |
[Pydanic](docs/pydanic.md) |
[API撰寫說明文檔](docs/api_guide.md) |
[爬蟲自動化說明文檔](docs/crawler.md) |
[AI機器人說明文檔](docs/ai_models.md) |
[新手開發注意事項](docs/beginner.md)



## 專案介紹
核心架構為 Python Web 框架，基於標準 Python 型別提示，內建 Swagger 互動式 API 文件。
結合資料庫MySQL與ORM，安全驗證 JSON Web Tokens bcrypt密碼加密、JWT、OPT驗證、雜湊，確保 API 傳輸安全性。並使用開發測試工具Ruff、pytest-asyncio、Black。

![FastAPI](https://img.shields.io/badge/FastAPI-0.127.0-05998b?logo=fastapi&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0.45-d71f00?logo=sqlalchemy&logoColor=white)
![PyMySQL](https://img.shields.io/badge/PyMySQL-1.1.2-4479a1?logo=mysql&logoColor=white)
![python-jose](https://img.shields.io/badge/python--jose-3.5.0-000000?logo=jsonwebtokens&logoColor=white)
![Bcrypt](https://img.shields.io/badge/Bcrypt-5.0.0-3776ab?logo=python&logoColor=white)
![Ruff](https://img.shields.io/badge/Ruff-0.14.10-d7ff64?logo=ruff&logoColor=black)
![pytest-asyncio](https://img.shields.io/badge/pytest--asyncio-1.3.0-0A9EDC?logo=pytest&logoColor=white)
![Black](https://img.shields.io/badge/Black-25.12.0-000000?logo=python&logoColor=white)


# 遷移專案說明：
- 必須重新 Clone
- 因為專案歷史紀錄已重整以抹除敏感資訊，請務必執行以下動作：
- 步驟 A：直接刪除您電腦中原本舊的 money-api 資料夾。原本的.env先複製內容下來，等下新clone的.env內容直接換成這個就好。
- 步驟 B：重新執行 Clone：
git clone https://github.com/4team-mma/money-api.git

- 步驟 C  Clone 專案 並進入資料夾。
## 啟動與安裝依賴流程
- 複製環境變數env.example 改成 .env (並填入自己的資料庫資訊)。(直接貼上你剛複製的.env程式碼)

## 安裝套件:
- 範例: uv add <package-name>
- 原本: pip install apscheduler
- uv add apscheduler  (定時自動執行任務的套件)
- uv add xmltodict apscheduler requests(XML與排程套件)
- uv add google-auth
- uv add slowapi(IP 限制套件)
- uv add pandas openpyxl (資料處理/Excel 檔案引擎)
- uv add reportlab (PDF轉換套件)
- uv add google-genai (Google 的 AI 套件)

## 移除套件:
- 執行:uv remove google-generativeai

# 安裝依賴:
- 執行：uv sync 
- macOS電腦如果執行./dev.sh不允許  請先使用：chmod +x dev.sh
- 如有更新套件,更新完git記得執行 uv sync 就可以自動補齊缺少的套件

-------------------------------------------------------------------------
開發內容:
- 開發 API：請去 routes/ 找對應自己的檔案，不要動 models.py，請在裡面實現 CRUD 功能。
- 測試：打開 http://127.0.0.1:8000/docs 確認 API 能動。
- API 測試：請確保在 /docs 測試成功後再進行 git commit。

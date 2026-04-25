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
[新手開發注意事項](docs/beginner.md)  |
[開發維護key手冊](docs/DEVELOPER_SECURITY.md)  |



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

## 安裝共用套件:
- 範例: uv add <package-name>
- 原本: pip install apscheduler
- uv add apscheduler  (定時自動執行任務的套件)
- uv add xmltodict apscheduler requests(XML與排程套件)
- uv add google-auth
- uv add slowapi(IP 限制套件)
- uv add pandas openpyxl (資料處理/Excel 檔案引擎)
- uv add reportlab (PDF轉換套件)
- uv add google-genai (Google 的 AI 套件)
- uv add user-agents  (「自動辨識裝置」的功能_例如win11)
- uv add pytz (是一個專門處理全球時區的資料庫，它能確保不論妳的伺服器是在 Google 雲端（通常在美國或日本）還是在地端，都能準確轉換成 台北時間 (Asia/Taipei)。)
- uv add line-bot-sdk python-dotenv #負責 LINE Bot 官方 API 串接，以及讀取 .env 檔案中的機密環境變數（金鑰）。
2026.03.20更新：
- uv add transformers soundfile # 處理音訊檔案或語音辨識,transformers 是處理機器學習模型的基礎套件。
- uv add torch torchaudio # 運算矩陣提取音訊特徵
- uv add pydantic langchain-core # AI系統的核心。pydantic 負責嚴格檢驗資料格式
- uv add langchain-community tiktoken # 社群擴充工具箱。我們用它來讀取 Markdown 格式的系統手冊 (TextLoader)。
- uv add langchain-chroma chromadb # 負責當「系統手冊的圖書館管理員」。chromadb 是存放向量數字的資料庫本體，langchain-chroma 是讓 AI 能去圖書館借書的溝通套件。
- uv add langchain-huggingface # 連接 Hugging Face 雲端算力。負責將我們寫的人類手冊文字，轉換成電腦看得懂的「向量數字 (Embedding)」，是 RAG (檢索增強生成) 的關鍵引擎。
- uv add langchain-groq #負責極速且精準的記帳 JSON 轉換
- uv add langchain-chroma langchain-community langchain-text-splitters
- uv add jieba # 詞彙級切割
2026.03.30更新：
- uv add customtkinter
- uv add pyinstaller
2026.04.02更新:
- uv add anthropic # 育育更新
- uv add pre-commit --dev # key檢查機器人:需放在根目錄
- uv add detect-secrets --dev # 檢查白名單
- uv add groq
- uv add langchain_ollama(AI輔助需要 )
2026.04.15更新：
- uv add langgraph 
- uv add langchain-core
2026.04.22更新：
- uv add fastembed (向量模型替代huggingface的)
->請重新執行rm -rf ./.chromadb (MacOS) ,win系列請執行rm -r -force .chromadb
或者:Remove-Item -Recurse -Force .chromadb
然後確認資料在不在要出現False，請輸入:Test-Path .chromadb
2026.0425更新:
- uv add "langchain-google-genai>=2.0.0"


## 非共用套件(改成開發環境安裝,就不會被部屬到雲端):
- uv add --dev peft accelerate
- uv pip install customtkinter requests pandas openpyxl
- uv pip install -U langchain-ollama(你要用後端AI輔助需要安裝)
- uv pip install locust (你要用模仿攻擊需要安裝)
- uv pip install peft accelerate 

### 如果要指定版本要加引號""
- uv add --dev "bitsandbytes>=0.46.1"
(QLoR外掛模型必備套件:Apeft是讀取(.safetensors)」的專用套件,accelerate是PyTorch 的官方擴充包)
- 自己電腦的套件請執行white_tool.bat


## 移除套件:
- 執行:uv remove google-generativeai
- uv remove spacy
- 移除非共用的套件:uv pip uninstall locust
- uv remove pynvml 

## 查套件:
- uv pip list
- pip show torch transformers peft accelerate
- uv pip show torch transformers peft accelerate

# 安裝依賴:
- 執行：uv sync
- macOS電腦如果執行./dev.sh不允許  請先使用：chmod +x dev.sh
- 如有更新套件,更新完git記得執行 uv sync 就可以自動補齊缺少的套件

-------------------------------------------------------------------------
開發內容:
- 開發 API：請去 routes/ 找對應自己的檔案，不要動 models.py，請在裡面實現 CRUD 功能。
- 測試：打開 http://127.0.0.1:8000/docs 確認 API 能動。
- API 測試：請確保在 /docs 測試成功後再進行 git commit。

-------------------------------------------------------------------------
# 補充說明:
- 因為雲端render是免費版,有限制,所以為了不衝突,第一次請在requirements.txt新增該內容:
```bash
# --- 基礎網路、網頁與模板 ---
fastapi>=0.115.0
uvicorn[standard]
python-multipart>=0.0.7
email-validator>=2.0.0
jinja2>=3.1.0

# --- 資料庫 & 安全 ---
sqlalchemy>=2.0.45
pymysql>=1.1.2
python-dotenv>=1.2.1
python-jose[cryptography]>=3.3.0
bcrypt>=5.0.0
line-bot-sdk>=3.22.0

# --- AI 與 資料處理 ---
google-genai>=1.62.0
langchain-groq>=1.1.2
langchain-community>=0.4.1
pandas>=2.2.0
openpyxl>=3.1.5

# --- 暫時註解重型套件 (保持 Render 512MB 穩定) ---
# torch
# torchaudio
# transformers

# --- 其他必要工具 ---
apscheduler>=3.11.2
requests>=2.32.5
pytz>=2025.1
reportlab>=4.4.9
slowapi>=0.1.9
soundfile>=0.13.1
user-agents>=2.2.0
xmltodict>=1.0.2

```


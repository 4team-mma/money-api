# 專案結構說明 (Project Structure)
[回首頁](../README.md)<br>
本專案為後端 API 服務，主要採用 Python 開發，並使用 web_app 作為核心邏輯目錄。

    .
    ├── .github/                # GitHub 配置
    ├── .venv/                  # Python 虛擬環境目錄 (Virtual Environment)
    ├── docs/                   # 專案相關說明文件與 API 文件
    ├── logs/                   # 系統執行日誌 (Logs)
    ├── web_app/                # API 原始碼主目錄
    │   ├── models/             # 資料庫 ORM 模型 (SQLAlchemy)
    │   │   ├── __init__.py     # 模組初始化，暴露模型介面
    │   │   └── models.py       # 定義資料表結構 (Member, Account, AddRecord 等)
    │   ├── routes/             # API 路由定義 (Endpoints)
    │   │   ├── __init__.py     # 路由模組初始化
    │   │   ├── accounts.py     # 帳戶相關 API (開戶、查詢等)
    │   │   ├── admin.py        # 管理員後台相關 API
    │   │   ├── auth.py         # 身分驗證 API (登入、Token 驗證)
    │   │   ├── records.py      # 紀錄/流水帳相關 API
    │   │   ├── reminders.py    # 提醒通知相關 API
    │   │   ├── root.py         # 根路由或基礎測試介面
    │   │   ├── transfers.py    # 轉帳/交易相關 API
    │   │   └── users.py        # 使用者基本資料管理 API
    │   ├── schemas/            # Pydantic 資料模型 (Request/Response 資料驗證)
    │   │   ├── __init__.py     # Schema 初始化
    │   │   ├── accounts.py     # 帳戶資料結構定義
    │   │   ├── add.py          # 新增收支紀錄用的 Schema
    │   │   ├── forgot_password.py # 忘記密碼流程的資料結構
    │   │   └── member.py       # 會員相關資料結構
    │   ├── services/           # 業務邏輯層 (預留處理複雜計算邏輯)
    │   ├── static/             # 靜態資源檔案 (如圖片、使用者頭像、favicon)
    │   ├── templates/          # 使用 Jinja2 模板 (暫時沒用到)
    │   ├── utils/              # 核心工具與通用邏輯
    │   │   ├── __init__.py     # 工具組初始化
    │   │   ├── email_utils.py  # 郵件發送工具
    │   │   ├── jwt.py          # JWT 加密與 Token 解析
    │   │   ├── otp.py          # OTP 驗證碼產生與驗證
    │   │   └── password.py     # 密碼 Bcrypt 雜湊演算法工具
    │   ├── __init__.py         # 將 web_app 標記為 Python 套件
    │   ├── database.py         # 資料庫連線配置 (Engine, Session)
    │   ├── dependencies.py     # FastAPI 依賴注入 (如：取得 DB、權限檢查)
    │   └── main.py             # 應用程式進入點 (App 初始化與路由掛載)
    ├── .env                    # 環境變數設定檔 (含資料庫密碼、密鑰等，不進入 Git)
    ├── .env.example            # 環境變數範例檔 (供團隊成員參考配置)
    ├── .gitignore              # Git 忽略檔案清單
    ├── .python-version         # 指定 Python 3.12 版本
    ├── dev.bat                 # Windows 開發環境啟動腳本 (uvicorn)
    ├── dev.sh                  # Linux/Mac 開發環境啟動腳本
    ├── pyproject.toml          # 專案依賴管理與 UV 配置
    ├── README.md               # 專案總覽說明
    ├── test_hash.py            # 密碼雜湊與驗證測試腳本
    └── uv.lock                 # 依賴版本鎖定檔案

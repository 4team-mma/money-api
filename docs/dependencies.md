# 專案使用套件說明
[回首頁](../README.md)

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

## 安裝生產環境依賴

```bash
pip install "fastapi[all]" sqlalchemy pymysql python-jose[cryptography] bcrypt
pnpm pip install ruff black pytest pytest-asyncio
```
## 安裝環境依賴
```bash
uv sync install
```
## 執行專案(執行前先設定好 .env 檔案。)
```bash
./dev.bat
```
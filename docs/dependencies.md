# 專案使用套件說明
[回首頁](../README.md)



## 安裝生產環境依賴

-- cryptography是加密工具，用於 「API Key」。它是雙向的。當你要呼叫 Gemini API 時，後端必須能將資料庫裡的密文「解密」回明文，才能傳送給 Google。

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

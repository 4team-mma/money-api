# 檔案位置：MONEY-API/run_crawler.py
# 執行方式:python run_crawler.py
import sys
import os

# 確保 Python 能找到 web_app 資料夾
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from web_app.utils.cpi_crawler import fetch_and_update_cpi

if __name__ == "__main__":
    print("🚀 手動啟動 CPI 爬蟲...")
    fetch_and_update_cpi()
    print("✅ 執行完畢，請檢查資料庫 cpi_data 表格。")
# 檔案位置：MONEY-API/run_crawler_salary.py

# 執行方式:python run_crawler_salary.py

import sys
import os

# 確保 Python 能找到 web_app 資料夾
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from web_app.utils.salary_crawler import run_all_salary_tasks

if __name__ == "__main__":
    print("🚀 手動啟動 薪資 數據爬取與清理任務...")
    # 💡 修正：執行正確的函式名稱
    run_all_salary_tasks()
    print("✅ 執行完畢，請檢查資料庫 salary_benchmarks 表格。")

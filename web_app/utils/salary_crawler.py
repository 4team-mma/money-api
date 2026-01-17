import requests
import xmltodict
import urllib3
from datetime import datetime
from ..database import SessionLocal
from ..models import SalaryBenchmark
import re

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL_REGULAR_9663 = "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230037/mp05002.xml"
URL_TOTAL_9634 = "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230037/mp05001.xml"

def clean_industry_name(raw_tag):
    return raw_tag.split('_')[0]

def fetch_salary_data(url, salary_type_name, is_real_val, xml_root_tag):
    print(f"--- [薪資爬蟲啟動: {salary_type_name}] ---")
    db = SessionLocal()
    current_year = datetime.now().year
    min_save_year = current_year - 5 
    
    try:
        response = requests.get(url, timeout=30, verify=False)
        response.encoding = 'utf-8'
        data_dict = xmltodict.parse(response.text)
        
        root = data_dict.get('DataCollection', {})
        records = root.get(xml_root_tag, [])
        
        if not isinstance(records, list):
            records = [records]

        new_count = 0
        update_count = 0
        for rec in records:
            raw_period = rec.get('年月別_Year_and_month')
            if not raw_period: continue
            
            # 1. 處理政府符號 (如 Ⓟ) 並提取數字
            digits = re.sub(r'\D', '', raw_period) 
            
            # 2. 統一格式化為 YYYYMXX (例如 2025M11)
            if len(digits) >= 6:
                year = digits[:4]
                month = digits[4:6]
                period_str = f"{year}M{month}"
            else:
                year = digits[:4]
                period_str = f"{year}M01"

            # 3. 過濾舊資料
            if int(year) < min_save_year:
                continue

            for key, val in rec.items():
                if key in ['年月別_Year_and_month', '@xmlns:xsi', '@xsi:noNamespaceSchemaLocation'] or not val or val == '-':
                    continue
                
                industry_name = clean_industry_name(key)
                
                # 4. 💡 改進點：檢查是否已存在
                existing = db.query(SalaryBenchmark).filter(
                    SalaryBenchmark.industry == industry_name,
                    SalaryBenchmark.period == period_str,
                    SalaryBenchmark.salary_type == salary_type_name,
                    SalaryBenchmark.salary_is_real == is_real_val
                ).first()

                if existing:
                    # 💡 如果重複了，就更新數值 (通常後面的數值包含獎金，更具參考價值)
                    existing.salary_val = float(val)
                    update_count += 1
                else:
                    db.add(SalaryBenchmark(
                        industry=industry_name,
                        period=period_str,
                        salary_type=salary_type_name,
                        salary_is_real=is_real_val,
                        salary_val=float(val)
                    ))
                    db.flush() # 🌟 關鍵：讓同一個 Session 內之後的查詢能看到這筆
                    new_count += 1
        
        db.commit()
        print(f"--- [{salary_type_name}] 結束。新增: {new_count} 筆, 更新: {update_count} 筆 ---")
    except Exception as e:
        db.rollback()
        print(f"❌ 抓取失敗: {e}")
    finally:
        db.close()

def run_all_salary_tasks():
    fetch_salary_data(URL_REGULAR_9663, "經常性薪資", 0, "每人每月經常性薪資")
    fetch_salary_data(URL_TOTAL_9634, "總薪資", 0, "每人每月總薪資")
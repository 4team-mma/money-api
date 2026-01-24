import requests
import xmltodict
import urllib3
import logging
from datetime import datetime
from ..database import SessionLocal
from ..models import SalaryBenchmark
import re

# 1. 取得與 main.py 一致的 logger
logger = logging.getLogger(__name__)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 政府開放資料 URL
URL_REGULAR_9663 = "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230037/mp05002.xml"
URL_TOTAL_9634 = "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230037/mp05001.xml"

def clean_industry_name(raw_tag):
    return raw_tag.split('_')[0]

def fetch_salary_data(url, salary_type_name, is_real_val, xml_root_tag):
    logger.info(f"🚀 開始抓取薪資數據: {salary_type_name}")
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
            if len(digits) >= 6:
                year, month = digits[:4], digits[4:6]
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

                try:
                    salary_val = float(val)
                    if existing:
                        # 💡 如果重複了，就更新數值 (通常後面的數值包含獎金，更具參考價值)
                        existing.salary_val = salary_val
                        update_count += 1
                    else:
                        db.add(SalaryBenchmark(
                            industry=industry_name,
                            period=period_str,
                            salary_type=salary_type_name,
                            salary_is_real=is_real_val,
                            salary_val=salary_val
                        ))
                        db.flush() # 🌟 關鍵：讓同一個 Session 內之後的查詢能看到這筆
                        new_count += 1
                except ValueError:
                    continue # 跳過非數字數值
        
        db.commit()
        logger.info(f"✅ {salary_type_name} 同步完成。新增: {new_count} 筆, 更新: {update_count} 筆 ---")
        
    except Exception as e:
        db.rollback()
        # 🌟 這裡使用 exc_info=True，Log 會紀錄哪一行爬蟲出錯
        logger.error(f"❌ 薪資抓取失敗 ({salary_type_name}): {str(e)}", exc_info=True)
    finally:
        db.close()

def run_all_salary_tasks():
    fetch_salary_data(URL_REGULAR_9663, "經常性薪資", 0, "每人每月經常性薪資")
    fetch_salary_data(URL_TOTAL_9634, "總薪資", 0, "每人每月總薪資")
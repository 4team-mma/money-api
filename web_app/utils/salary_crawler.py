import requests
import xmltodict
import urllib3
import logging
from datetime import datetime, timedelta

from decimal import Decimal
from sqlalchemy import desc
from ..database import SessionLocal
from ..models import SalaryBenchmark
import re

# 1. 取得與 main.py 一致的 logger
logger = logging.getLogger(__name__)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 政府開放資料 URL
URL_REGULAR_9663 = (
    "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230037/mp05002.xml"
)
URL_TOTAL_9634 = (
    "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230037/mp05001.xml"
)


def clean_industry_name(raw_tag):
    return raw_tag.split("_")[0]


def fetch_salary_data(url, salary_type_name, is_real_val, xml_root_tag):
    logger.info(f"🚀 開始抓取薪資數據: {salary_type_name}")
    
    # ✅ 修正 1: 確保變數有先定義
    current_date = datetime.now()
    current_year = current_date.year
    min_save_year = current_year - 5
    
    # --- 判斷邏輯 (Smart Check) ---
    # 薪資資料通常比 CPI 慢，可能延遲 2 個月左右
    # 我們這裡簡單判斷：只要資料庫有今年(或上個月)的資料，就算更新過了
    with SessionLocal() as db:
        latest_record = (
            db.query(SalaryBenchmark)
            .filter(SalaryBenchmark.salary_type == salary_type_name)
            .order_by(SalaryBenchmark.period.desc())
            .first()
        )
        
        # 取得上個月的日期字串 (例如 2026M01)
        last_month_date = current_date.replace(day=1) - timedelta(days=1)
        target_period_str = last_month_date.strftime("%YM%m")

        if latest_record and latest_record.period >= target_period_str:
            msg = f"✅ [薪資爬蟲] {salary_type_name} 資料已是最新 ({latest_record.period})，跳過。"
            logger.info(msg)
            print(msg) # 💡 直接顯示在終端機
            return

    # --- 若沒通過檢查，開始爬蟲 ---
    db = SessionLocal()
    try:
        response = requests.get(url, timeout=30, verify=False)
        response.encoding = "utf-8"
        
        # 簡單檢查 XML 是否有效
        if response.status_code != 200:
            logger.error(f"❌ 無法下載薪資資料: {url}")
            return

        data_dict = xmltodict.parse(response.text)
        root = data_dict.get("DataCollection", {})
        records = root.get(xml_root_tag, [])

        if not isinstance(records, list):
            records = [records]

        new_count = 0
        update_count = 0
        
        for rec in records:
            raw_period = rec.get("年月別_Year_and_month")
            if not raw_period:
                continue

            # 1. 處理政府符號 (如 Ⓟ) 並提取數字
            digits = re.sub(r"\D", "", raw_period)
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
                if (
                    key in [
                        "年月別_Year_and_month",
                        "@xmlns:xsi",
                        "@xsi:noNamespaceSchemaLocation",
                    ]
                    or not val
                    or val == "-"
                ):
                    continue

                industry_name = clean_industry_name(key)

                # 4. 檢查是否已存在
                existing = (
                    db.query(SalaryBenchmark)
                    .filter(
                        SalaryBenchmark.industry == industry_name,
                        SalaryBenchmark.period == period_str,
                        SalaryBenchmark.salary_type == salary_type_name,
                        SalaryBenchmark.salary_is_real == is_real_val,
                    )
                    .first()
                )

                try:
                    # ✅ 修正 2: 改用 Decimal，解決 Pylance 報錯
                    salary_val_decimal = Decimal(val)

                    if existing:
                        # 如果數值不同才更新
                        if existing.salary_val != salary_val_decimal:
                            existing.salary_val = salary_val_decimal
                            update_count += 1
                    else:
                        db.add(
                            SalaryBenchmark(
                                industry=industry_name,
                                period=period_str,
                                salary_type=salary_type_name,
                                salary_is_real=is_real_val,
                                salary_val=salary_val_decimal,
                            )
                        )
                        # ✅ 修正 3 (關鍵): 加入 flush() 避免 Duplicate Entry 報錯
                        db.flush()
                        
                        new_count += 1
                except ValueError:
                    continue 
                except Exception:
                    continue

        db.commit()
        success_msg = f"✅ [薪資爬蟲] {salary_type_name} 更新完成。新增: {new_count}, 更新: {update_count}"
        logger.info(success_msg)
        print(success_msg) # 💡 顯示在終端機

    except Exception as e:
        db.rollback()
        logger.error(f"❌ 薪資抓取失敗 ({salary_type_name}): {str(e)}", exc_info=True)
    finally:
        db.close()


def run_all_salary_tasks():
    fetch_salary_data(URL_REGULAR_9663, "經常性薪資", 0, "每人每月經常性薪資")
    fetch_salary_data(URL_TOTAL_9634, "總薪資", 0, "每人每月總薪資")
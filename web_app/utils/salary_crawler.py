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
URL_REGULAR_9663 = "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230037/mp05002.xml"
URL_TOTAL_9634 = "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230037/mp05001.xml"


def clean_industry_name(raw_tag):
    return raw_tag.split("_")[0]


def fetch_salary_data(url, salary_type_name, is_real_val, xml_root_tag):
    logger.info(f"🚀 開始抓取薪資數據: {salary_type_name}")
    
    current_date = datetime.now()
    current_year = current_date.year
    min_save_year = current_year - 5
    
    with SessionLocal() as db:
        # 🌟 核心優化：取得資料庫中目前「最新」的年月 (例如 "2026M01")
        latest_record = (
            db.query(SalaryBenchmark)
            .filter(SalaryBenchmark.salary_type == salary_type_name)
            .order_by(SalaryBenchmark.period.desc())
            .first()
        )
        
        # 如果資料庫沒資料，就從 5 年前開始算；如果有，就把最新的月份記下來
        db_latest_period = latest_record.period if latest_record else f"{min_save_year}M01"

        # 原本的 Smart Check 保留，用來做最外層的攔截
        last_month_date = current_date.replace(day=1) - timedelta(days=1)
        target_period_str = last_month_date.strftime("%YM%m")

        if latest_record and latest_record.period >= target_period_str:
            msg = f"✅ [薪資爬蟲] {salary_type_name} 資料已是最新 ({latest_record.period})，跳過。"
            logger.info(msg)
            print(msg) 
            return

    # --- 若沒通過檢查，開始爬蟲 ---
    db = SessionLocal()
    try:
        response = requests.get(url, timeout=30, verify=False)
        response.encoding = "utf-8"
        
        if response.status_code != 200:
            logger.error(f"❌ 無法下載薪資資料: {url}")
            return

        # ✅ 修正 Pylance 報錯：使用 or 確保就算解析出 None，也會變成預設的字典或陣列
        data_dict = xmltodict.parse(response.text) or {}
        root = data_dict.get("DataCollection") or {}
        records = root.get(xml_root_tag) or []

        if not isinstance(records, list):
            records = [records]

        new_count = 0
        update_count = 0
        
        for rec in records:
            raw_period = rec.get("年月別_Year_and_month")
            if not raw_period:
                continue

            digits = re.sub(r"\D", "", raw_period)
            if len(digits) >= 6:
                year, month = digits[:4], digits[4:6]
                period_str = f"{year}M{month}"
            else:
                year = digits[:4]
                period_str = f"{year}M01"

            # 🌟 核心優化 2：如果這筆資料的月份「早於」資料庫最新的月份，直接跳過！
            # 這行可以直接省下幾千次的資料庫查詢
            if period_str < db_latest_period:
                continue

            if int(year) < min_save_year:
                continue

            for key, val in rec.items():
                if (
                    key in ["年月別_Year_and_month", "@xmlns:xsi", "@xsi:noNamespaceSchemaLocation"]
                    or not val
                    or val == "-"
                ):
                    continue

                industry_name = clean_industry_name(key)

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
                    salary_val_decimal = Decimal(val)

                    if existing:
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
                        db.flush()
                        
                        new_count += 1
                except ValueError:
                    continue 
                except Exception:
                    continue

        db.commit()
        success_msg = f"✅ [薪薪爬蟲] {salary_type_name} 更新完成。新增: {new_count}, 更新: {update_count}"
        logger.info(success_msg)
        print(success_msg)

    except Exception as e:
        db.rollback()
        logger.error(f"❌ 薪資抓取失敗 ({salary_type_name}): {str(e)}", exc_info=True)
    finally:
        db.close()


def run_all_salary_tasks():
    fetch_salary_data(URL_REGULAR_9663, "經常性薪資", 0, "每人每月經常性薪資")
    fetch_salary_data(URL_TOTAL_9634, "總薪資", 0, "每人每月總薪資")
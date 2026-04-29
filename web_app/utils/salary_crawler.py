# salary_crawler.py
import requests
import xmltodict
import urllib3
import logging
import time
from datetime import datetime, timedelta
from decimal import Decimal
from ..database import SessionLocal
from ..models import SalaryBenchmark, TaskRunLog
import re

logger = logging.getLogger(__name__)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL_REGULAR_9663 = "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230037/mp05002.xml"
URL_TOTAL_9634 = "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230037/mp05001.xml"


def clean_industry_name(raw_tag):
    return raw_tag.split("_")[0]


# ── 工具：寫入一筆執行紀錄（與 cpi_crawler 同樣設計）──────────
def _write_log(task_name: str, status: str, duration_ms: int = 0,
               rows_added: int = 0, rows_updated: int = 0,
               message: str = ""):
    """獨立 session 寫入，不受主程式 rollback 影響"""
    try:
        with SessionLocal() as log_db:
            log_db.add(TaskRunLog(
                task_name=task_name,
                status=status,
                duration_ms=duration_ms,
                rows_added=rows_added,
                rows_updated=rows_updated,
                message=message[:200] if message else "",
            ))
            log_db.commit()
    except Exception as log_err:
        logger.error(f"[Salary] 寫入 task_run_log 失敗: {log_err}")


# ── 單一薪資類型爬蟲 ─────────────────────────────────────────────
def fetch_salary_data(url: str, salary_type_name: str,
                      is_real_val: int, xml_root_tag: str):
    logger.info(f"🚀 開始抓取薪資數據: {salary_type_name}")
    start_time = time.time()

    # task_name 格式：salary_經常性薪資 / salary_總薪資
    task_name = f"salary_{salary_type_name}"

    current_date = datetime.now()
    current_year = current_date.year
    min_save_year = current_year - 5

    # ── 智慧跳過：用獨立 session 查詢，避免後面爬蟲用同一個 session ──
    with SessionLocal() as check_db:
        latest_record = (
            check_db.query(SalaryBenchmark)
            .filter(SalaryBenchmark.salary_type == salary_type_name)
            .order_by(SalaryBenchmark.period.desc())
            .first()
        )

        db_latest_period = (
            latest_record.period if latest_record
            else f"{min_save_year}M01"
        )

        last_month_date = current_date.replace(day=1) - timedelta(days=1)
        # 允許落後一個月（薪資資料通常比 CPI 晚發布）
        two_months_ago = (
            last_month_date.replace(day=1) - timedelta(days=1)
        ).strftime("%YM%m")

        if latest_record and latest_record.period >= two_months_ago:
            msg = (
                f"{salary_type_name} 資料已是最新 "
                f"({latest_record.period})，跳過"
            )
            logger.info(f"✅ [薪資爬蟲] {msg}")
            print(f"✅ [薪資爬蟲] {msg}")

            # ★ 寫入 skip 紀錄
            _write_log(
                task_name=task_name,
                status="skip",
                duration_ms=int((time.time() - start_time) * 1000),
                message=msg,
            )
            return

    # ── 正式爬蟲邏輯 ─────────────────────────────────────────────
    db = SessionLocal()
    try:
        response = requests.get(url, timeout=30, verify=False)
        response.encoding = "utf-8"

        if response.status_code != 200:
            msg = f"HTTP {response.status_code}，無法下載薪資資料"
            logger.error(f"❌ {msg}: {url}")

            # ★ 寫入 fail 紀錄
            _write_log(
                task_name=task_name,
                status="fail",
                duration_ms=int((time.time() - start_time) * 1000),
                message=msg,
            )
            return

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

            # 早於資料庫最新月份的直接跳過，省下大量 DB 查詢
            if period_str < db_latest_period:
                continue

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
                        db.add(SalaryBenchmark(
                            industry=industry_name,
                            period=period_str,
                            salary_type=salary_type_name,
                            salary_is_real=is_real_val,
                            salary_val=salary_val_decimal,
                        ))
                        db.flush()
                        new_count += 1

                except ValueError:
                    continue
                except Exception:
                    continue

        db.commit()
        duration_ms = int((time.time() - start_time) * 1000)
        success_msg = (
            f"{salary_type_name} 更新完成。"
            f"新增: {new_count} 筆, 更新: {update_count} 筆"
        )
        logger.info(f"✅ [薪資爬蟲] {success_msg} ({duration_ms}ms)")
        print(f"✅ [薪資爬蟲] {success_msg}")

        # ★ 寫入 ok 紀錄
        _write_log(
            task_name=task_name,
            status="ok",
            duration_ms=duration_ms,
            rows_added=new_count,
            rows_updated=update_count,
            message=success_msg,
        )

    except Exception as e:
        db.rollback()
        duration_ms = int((time.time() - start_time) * 1000)
        err_msg = str(e)[:200]
        logger.error(
            f"❌ 薪資抓取失敗 ({salary_type_name}): {err_msg}",
            exc_info=True,
        )

        # ★ 寫入 fail 紀錄
        _write_log(
            task_name=task_name,
            status="fail",
            duration_ms=duration_ms,
            message=err_msg,
        )

    finally:
        db.close()


# ── 對外入口：兩種薪資類型一起跑 ────────────────────────────────
def run_all_salary_tasks():
    fetch_salary_data(URL_REGULAR_9663, "經常性薪資", 0, "每人每月經常性薪資")
    fetch_salary_data(URL_TOTAL_9634, "總薪資", 0, "每人每月總薪資")
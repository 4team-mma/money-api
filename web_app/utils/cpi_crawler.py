import requests
import xmltodict
import urllib3
import re
from datetime import datetime
from ..models import CpiData
from ..database import SessionLocal

# 屏蔽安全警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 政府 CPI 月資料連結
CPI_URL = "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230555/pr0101a1m.xml"

def find_data_items(obj):
    """💡 強效搜尋：自動在 XML 字典結構中尋找資料列表"""
    if isinstance(obj, list):
        if len(obj) > 0 and isinstance(obj[0], dict) and 'Item' in obj[0]:
            return obj
        for item in obj:
            res = find_data_items(item)
            if res: return res
    if isinstance(obj, dict):
        for target in ['pr0101a1m', 'Row', 'pr0101a1']:
            if target in obj:
                val = obj[target]
                return val if isinstance(val, list) else [val]
        for k, v in obj.items():
            if k.startswith('@'): continue 
            res = find_data_items(v)
            if res: return res
    return []

def fetch_and_update_cpi():
    """
    抓取 CPI 指數並存入資料庫，僅保留最近 6 年數據。
    """
    print("--- [CPI 爬蟲啟動: 6 年過濾版] ---")
    db = SessionLocal()
    current_year = datetime.now().year
    # 💡 嚴格限制：只抓取今年起算前 6 年 (如 2021-2026)
    min_save_year = current_year - 5 
    
    try:
        response = requests.get(CPI_URL, timeout=30, verify=False)
        response.encoding = 'utf-8'
        data_dict = xmltodict.parse(response.text)
        
        items = find_data_items(data_dict)

        if not items:
            print("❌ 錯誤：無法在 XML 結構中找到資料節點。")
            return

        new_count = 0
        update_count = 0
        skip_count = 0

        for item in items:
            category_name = item.get('Item')
            raw_period = item.get('TIME_PERIOD') 
            type_val = item.get('TYPE')           
            value = item.get('Item_VALUE')

            if not value or value == '-' or not category_name: 
                continue

            # 1. 💡 年份過濾邏輯：只處理 2021 年以後的資料
            year_part = int(raw_period[:4])
            if year_part < min_save_year:
                skip_count += 1
                continue

            # 2. 💡 格式清理：移除初步統計符號 (如 Ⓟ) 以便與薪資表關聯
            period_str = re.sub(r'[^0-9M]', '', raw_period) 

            # 3. 💡 Upsert 邏輯 (檢查是否存在)
            existing = db.query(CpiData).filter(
                CpiData.category == category_name,
                CpiData.period == period_str,
                CpiData.data_type == type_val
            ).first()

            val_float = float(value)

            if not existing:
                db.add(CpiData(
                    category=category_name,
                    period=period_str,
                    data_type=type_val,
                    val=val_float
                ))
                new_count += 1
            else:
                if float(existing.val) != val_float:
                    existing.val = val_float
                    update_count += 1
            
            if (new_count + update_count) % 500 == 0:
                db.flush()

        db.commit()
        print(f"--- [CPI 任務結束] 新增: {new_count} 筆, 更新: {update_count} 筆, 跳過舊資料: {skip_count} 筆 ---")

    except Exception as e:
        db.rollback()
        print(f"❌ 抓取失敗: {e}")
    finally:
        db.close()
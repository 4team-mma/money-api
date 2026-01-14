import requests
import xmltodict
from sqlalchemy.orm import Session
from ..models import CpiData  # 假設你有建立對應的 SQLAlchemy Model
from ..database import SessionLocal

CPI_URL = "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230555/pr0101a1m.xml"

def fetch_and_update_cpi():
    print("開始抓取 CPI 資料...")
    try:
        response = requests.get(CPI_URL)
        response.encoding = 'utf-8' # 確保編碼正確
        
        # 1. XML 轉 Dict (JSON 結構)
        data_dict = xmltodict.parse(response.text)
        
        # 政府資料結構通常比較深，需要根據實際 XML 結構調整路徑
        # 假設結構是 Table -> Row
        items = data_dict.get('Table', {}).get('Row', [])
        
        db = SessionLocal()
        
        for item in items:
            # 取得欄位 (需依照實際 XML 標籤名稱調整)
            category_name = item.get('Item')
            time_period = item.get('TIME_PERIOD')
            type_val = item.get('TYPE')
            value = item.get('Item_VALUE')

            # 簡單過濾：我們可能只需要 "年增率" 或 "指數"
            if not value: 
                continue

            # 2. Upsert (有則更新，無則新增)
            # 這裡建議使用 SQLAlchemy 的 merge 或是先查詢後寫入
            existing = db.query(CpiData).filter(
                CpiData.category == category_name,
                CpiData.period == time_period,
                CpiData.data_type == type_val
            ).first()

            if not existing:
                new_cpi = CpiData(
                    category=category_name,
                    period=time_period,
                    data_type=type_val,
                    val=float(value)
                )
                db.add(new_cpi)
            else:
                existing.val = float(value) # 更新數值
        
        db.commit()
        db.close()
        print("CPI 資料更新完成")

    except Exception as e:
        print(f"抓取失敗: {e}")
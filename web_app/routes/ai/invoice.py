from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
import shutil
import os

from web_app.database import get_db
from web_app.schemas.invoice import TaiwanUniformInvoice
from ...models.models import Invoice, Member , InvoiceItem # 確保路徑正確
from ...dependencies import get_current_user
from web_app.services.invoice_service import InvoiceService

router = APIRouter()

# --- 路由 1：AI 圖片辨識 (只辨識，不存檔) ---
@router.post("/analyze")
async def analyze_invoice(
    file: UploadFile = File(...), 
    db: Session = Depends(get_db), 
    current_user: Member = Depends(get_current_user)
):
    # 1. 準備路徑 (放在 try 之外是安全的，但 try 要緊跟在後)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    temp_dir = os.path.normpath(os.path.join(current_dir, "../../../temp"))
    os.makedirs(temp_dir, exist_ok=True)
    temp_file_path = os.path.join(temp_dir, f"user_{current_user.user_id}_{file.filename}")

    try:
        # 2. 儲存檔案 (放入 try 區塊內，確保出事能清理)
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # 3. 執行辨識
        result = await InvoiceService.extract_invoice_data(
            db=db, 
            user_id=current_user.user_id, 
            image_path=temp_file_path
        )
        return {"success": True, "data": result}
        
    except Exception as e:
        # 4. 捕捉錯誤並提取 raw_reply
        detail_msg = f"辨識失敗：{str(e)}"
        raw_data = getattr(e, 'raw_reply', None) # 使用 getattr 更安全
        
        # 確保 raw_data 轉換成字串，避免 serializable 報錯
        if raw_data is not None:
            raw_data = str(raw_data)
            
        raise HTTPException(
            status_code=500, 
            detail={
                "message": detail_msg,
                "raw_result": raw_data  # 🎯 這裡會顯示 AI 壞掉的 JSON 字串
            }
        )
    finally:
        # 5. 無論成功失敗，一定要刪除暫存檔
        if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
            os.remove(temp_file_path)


# --- 路由 2：正式存入資料庫 (確認後觸發) ---
@router.post("/invoices/")
def create_invoice(
    invoice_data: TaiwanUniformInvoice, 
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    """
    接收前端確認後的資料，正式寫入 MySQL。
    """
    try:
        data_dict = invoice_data.model_dump()

        # items 要單獨處理，不能直接丟給 Invoice()
        items_data = data_dict.pop("items", None)

        # 建立發票主表
        new_invoice = Invoice(
            **data_dict,
            user_id=current_user.user_id
        )
        db.add(new_invoice)
        db.flush()  # 先取得 invoice_id，還不 commit

        # 建立商品明細（如果有的話）
        if items_data:
            for item in items_data:
                new_item = InvoiceItem(
                    invoice_id=new_invoice.invoice_id,
                    name=item["name"],
                    quantity=item.get("quantity"),
                    unit_price=item.get("unit_price"),
                    subtotal=item.get("subtotal"),
                )
                db.add(new_item)

        db.commit()
        db.refresh(new_invoice)

        return {"success": True, "id": new_invoice.invoice_id}

    except Exception as e:
        db.rollback()
        print(f"DEBUG: 資料庫報錯內容 -> {str(e)}")
        raise HTTPException(status_code=500, detail="資料庫處理異常，請檢查統編或格式是否正確。") 
    
# # 在現有路由下方新增
# @router.post("/identify-product")
# async def identify_product(
#     file: UploadFile = File(...),
#     current_user: Member = Depends(get_current_user)
# ):
#     """
#     拍商品照片 → 回傳商品名稱、推估價格區間、分類建議
#     """
#     ALLOWED_TYPES = {"image/jpeg", "image/png", "image/heic", "image/webp"}
#     if file.content_type not in ALLOWED_TYPES:
#         raise HTTPException(400, "不支援的圖片格式")

#     raw_bytes = await file.read()
#     if len(raw_bytes) > 10 * 1024 * 1024:
#         raise HTTPException(400, "圖片超過 10MB")

#     # 前處理
#     image_b64 = InvoiceService._preprocess_image_from_bytes(raw_bytes)

#     # 呼叫 Claude 辨識商品
#     result = await InvoiceService.identify_product(image_b64)
#     return {"success": True, "data": result}
import os
import shutil
import logging
import asyncio
import json
import re  
import numpy as np
import jieba
import onnxruntime as ort
import openpyxl
import csv
from decimal import Decimal
from fastapi import APIRouter, Depends, Body, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
# --- 內部模組引入 ---
from ...database import get_db
from ...models import Member, IntentReviewLog, AIConfig
from ...dependencies import get_current_user
from ...services.finance_agent_service import FinanceAgentService
from ...services.gemini_service import GeminiService
from ...services.ollama_service import OllamaService
from ...utils.ai_security import decrypt_api_key
from web_app.utils.security_guard import is_malicious

# 引入 ChromaDB 與 HuggingFace
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from langchain_core.documents import Document

load_dotenv()
router = APIRouter(tags=["AI 喵喵開發者工具"])
logger = logging.getLogger(__name__)

# --- 🎯 路徑定義 (修正 Pylance 紅線) ---
TEMP_DIR = "web_app/temp/excel"
DEFAULT_TEST_FILE = os.path.join(TEMP_DIR, "hard_cases.xlsx")
CURRENT_BATCH_FILE_BASE = os.path.join(TEMP_DIR, "current_test_batch") 
MODELS_DIR = "web_app/models/checkpoints"
CHROMA_DIR = ".chromadb"

def ensure_temp_dir():
    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR, exist_ok=True)

@router.post("/upload_test_file", summary="📤 上傳自定義測試 Excel")
async def upload_test_file(file: UploadFile = File(...), current_user: Member = Depends(get_current_user)):
    
    if current_user.role not in ["ai_test", "admin"]: raise HTTPException(status_code=403, detail="權限不足")
    
    # 🌟 1. 取得副檔名並判斷
    ext = os.path.splitext((file.filename or "").lower())[1]
    if ext not in [".xlsx", ".csv"]: 
        raise HTTPException(status_code=400, detail="僅支援 .xlsx 與 .csv 格式喵！")
    
    ensure_temp_dir()
    
    # 清空舊檔 (不要刪到 hard_cases.xlsx)
    for f in os.listdir(TEMP_DIR):
        if f.startswith("current_test_batch"):
            try: os.unlink(os.path.join(TEMP_DIR, f))
            except: pass
            
    # 🌟 2. 儲存時動態加上正確的副檔名
    save_path = CURRENT_BATCH_FILE_BASE + ext
    with open(save_path, "wb") as buffer: 
        shutil.copyfileobj(file.file, buffer)
        
    return {"success": True, "message": f"測試檔 {file.filename} 上傳成功！"}

@router.delete("/clear_test_file", summary="🗑️ 清除暫存的測試檔")
async def clear_test_file(current_user: Member = Depends(get_current_user)):
    if current_user.role not in ["ai_test", "admin"]: raise HTTPException(status_code=403, detail="權限不足")
    
    # 🌟 兩種副檔名都巡邏一遍，有就刪除
    for ext in [".xlsx", ".csv"]:
        path = CURRENT_BATCH_FILE_BASE + ext
        if os.path.exists(path): 
            os.remove(path)
            deleted = True
            
    if deleted: return {"success": True, "message": "已刪除喵！"}
    return {"success": True, "message": "無暫存檔。"}


# ==========================================
# 🧠 擂台專屬大腦管理器 (V2 終極同步版)
# ==========================================
class ArenaBrains:
    def __init__(self):
        # 初始預設值
        self.MAX_LEN = 40
        self.PADDING_TYPE = "post"
        self.v1_session = None
        self.v2_session = None
        self.v1_vocab = {}
        self.v2_vocab = {}
        self.v1_labels = []
        self.v2_labels = []
        self.chroma_store = None

        # 載入順序：先讀設定，再載模型
        self._load_config()
        self._load_models()

    def _load_config(self):
        """讀取 Jupyter 產出的環境設定檔"""
        config_path = os.path.join(MODELS_DIR, "brain_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    self.MAX_LEN = cfg.get("MAX_LEN", 40)
                    self.PADDING_TYPE = cfg.get("PADDING_TYPE", "post")
                    self.v2_labels = cfg.get("CLASSES", [])
                    logger.info(f"📡 已同步 Jupyter 環境：MAX_LEN={self.MAX_LEN}, PADDING={self.PADDING_TYPE}")
            except Exception as e:
                logger.error(f"❌ 讀取 brain_config 失敗: {e}")

    def _load_models(self):
        print(f"🔍 正在檢查模型目錄: {os.path.abspath(MODELS_DIR)}")
        try:
            # 1. 載入 V1 (舊版)
            v1_path = os.path.join(MODELS_DIR, "cupid_intent_model_v1.onnx")
            if os.path.exists(v1_path):
                self.v1_session = ort.InferenceSession(v1_path)
                with open(os.path.join(MODELS_DIR, "tokenizer_dict_v1.json"), "r", encoding="utf-8") as f:
                    self.v1_vocab = json.load(f)
                with open(os.path.join(MODELS_DIR, "label_map_v1.json"), "r", encoding="utf-8") as f:
                    self.v1_labels = json.load(f)

            # 2. 載入 V2 (邱比特重生版)
            v2_path = os.path.join(MODELS_DIR, "cupid_intent_model.onnx")
            if os.path.exists(v2_path):
                self.v2_session = ort.InferenceSession(v2_path)
                with open(os.path.join(MODELS_DIR, "tokenizer_dict.json"), "r", encoding="utf-8") as f:
                    self.v2_vocab = json.load(f)
                # 如果 config 沒抓到 labels，才讀取 label_map.json 補位
                if not self.v2_labels:
                    with open(os.path.join(MODELS_DIR, "label_map.json"), "r", encoding="utf-8") as f:
                        self.v2_labels = json.load(f)

            # 3. 載入 ChromaDB
            hf_token = os.getenv("HF_TOKEN")
            if hf_token and os.path.exists(CHROMA_DIR):
                embeddings = HuggingFaceEndpointEmbeddings(
                    model="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                    huggingfacehub_api_token=hf_token
                )
                self.chroma_store = Chroma(
                    collection_name="intent_examples",
                    embedding_function=embeddings,
                    persist_directory=CHROMA_DIR
                )
            logger.info("✅ 擂台大腦 (V1, V2, Chroma) 載入完成！")
        except Exception as e:
            logger.error(f"❌ 載入過程出錯: {e}")

    def _text_to_pad_seq(self, text, vocab):
        """將文字轉換為模型預期的 (1, 40) float32 矩陣"""
        words = jieba.lcut(text)
        seq = [vocab.get(w, 0) for w in words]
        input_array = np.zeros((1, self.MAX_LEN), dtype=np.float32)

        if self.PADDING_TYPE == "post":
            for i, word_id in enumerate(seq):
                if i >= self.MAX_LEN: break
                input_array[0, i] = float(word_id)
        else: # pre
            start_idx = max(0, self.MAX_LEN - len(seq))
            for i, word_id in enumerate(seq[-(self.MAX_LEN):]):
                input_array[0, start_idx + i] = float(word_id)
        return input_array

    def predict_v1(self, text: str):
        if not self.v1_session: return "UNKNOWN", 0.0
        input_data = self._text_to_pad_seq(text, self.v1_vocab)
        outputs = self.v1_session.run(None, {self.v1_session.get_inputs()[0].name: input_data})
        probs = np.array(outputs[0])[0]
        best_idx = int(np.argmax(probs))
        return self.v1_labels[best_idx], float(probs[best_idx])

    def predict_v2(self, text: str):
        if not self.v2_session: return "UNKNOWN", 0.0, False

        # [階段 1]：語意攔截 (ChromaDB)
        if self.chroma_store:
            try:
                docs = self.chroma_store.similarity_search_with_score(text, k=1)
                if docs and docs[0][1] < 0.4:
                    return docs[0][0].metadata["intent"], 1.0, True
            except: pass

        # [階段 2]：模型推論 (ONNX)
        input_data = self._text_to_pad_seq(text, self.v2_vocab)
        outputs = self.v2_session.run(None, {self.v2_session.get_inputs()[0].name: input_data})
        probs = np.array(outputs[0])[0]
        keras_intent = self.v2_labels[int(np.argmax(probs))]

        # [階段 3]：🌟 理科保鑣 (Regex) 修正誤判
        final_intent = keras_intent
        digit_groups = re.findall(r'\d+', text)
        money_strength = max(text.count('元') + text.count('塊'), len(digit_groups))

        # 🛡️ 規則 A：多項式強制升級 (例如一次出現兩個數字)
        if money_strength >= 2 and 'MULTI' not in final_intent:
            final_intent = 'MULTI_QUERY' if 'QUERY' in final_intent else 'MULTI_RECORD'
            return final_intent, 1.0, False

        # 🛡️ 規則 B：CHAT 閒聊攔截 (有錢數字但沒有動作動詞)
        action_keywords = ['買', '花', '吃', '喝', '付', '繳', '存', '記', '入', '支']
        has_action_verb = any(kw in text for kw in action_keywords)

        # 🌟 沒動作動詞，就算是天王老子(模型)說是 RECORD 也不准過
        if keras_intent == 'RECORD' and not has_action_verb:
            return "CHAT", 1.0, False

        return final_intent, float(np.max(probs)), False

arena_brains = ArenaBrains()

# 🏅 裁判：加權計分邏輯
def calculate_score(true_intent: str, pred_intent: str):
    t_base = true_intent.replace("MULTI_", "")
    p_base = pred_intent.replace("MULTI_", "")
    if true_intent == pred_intent: return 1.0
    if t_base == p_base: return 0.5
    borderlines = [{"ADVISOR", "CHAT"}, {"RECORD", "CHAT"}, {"QUERY", "ADVISOR"}, {"QUERY", "KNOWLEDGE"}, {"CHAT", "KNOWLEDGE"}]
    if {t_base, p_base} in borderlines: return 0.3
    return 0.0


async def get_reply(db: Session, user: Member, message: str, target_intent: str) -> str:
    """解決 Pylance 紅線與 Gemini 回傳字典問題"""
    try:
        ctx = await FinanceAgentService.get_context(db=db, user=user, message=message, override_intent=target_intent)
        system_prompt = ctx.get("system_prompt", "你是理財助手喵喵。")

        config = db.query(AIConfig).filter(AIConfig.user_id == user.user_id, AIConfig.is_active == True).first()
        if not config:
            config = db.query(AIConfig).filter(AIConfig.user_id == 1, AIConfig.is_active == True).first()

        provider = config.provider if config else "gemini"
        model_ver = config.model_version if config else "gemini-3-flash-preview"
        base_url = config.base_url if config else "http://localhost:11434"

        if provider == "ollama":
            reply_text = await OllamaService.chat_async(
                prompt=message,
                system_instruction=system_prompt,
                base_url=base_url,
                model_id=model_ver
            )
            return f"[Ollama - {model_ver}]\n{reply_text}"

        elif provider == "gemini":
            env_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            db_key = "none"
            if config and config.api_key and config.api_key != "none":
                try: db_key = decrypt_api_key(config.api_key)
                except: pass

            # 🌟 [關鍵修正] 解決 Pylance 紅線：確保 final_key 絕對是 str
            raw_key = db_key if (db_key and len(db_key) > 10) else env_key
            if raw_key is None:
                return "❌ 系統錯誤：找不到有效的 API Key"

            final_key: str = str(raw_key) # 強制轉型確保類型安全

            gemini_res = await GeminiService.chat_async(
                api_key=final_key,
                model_id=model_ver,
                prompt=message,
                system_instruction=system_prompt
            )
            # 🌟 [修正] GeminiService 回傳的是 dict，要取 ["text"]
            return f"[Gemini - {model_ver}]\n{gemini_res.get('text', '無回覆內容')}"

        return f"尚未支援 {provider} 的測試回覆喵~"

    except Exception as e:
        logger.error(f"❌ [get_reply] 出錯: {str(e)}")
        return f"生成失敗: {str(e)}"


# -------------------------------------------------------------------
# API 路由區
# -------------------------------------------------------------------

@router.get("/admin_logs", summary="👑 管理員：獲審核清單")
async def get_admin_review_logs(
    is_reviewed: int = Query(0),
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1),
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    if current_user.role not in ["admin"]: raise HTTPException(status_code=403, detail="權限不足")
    query = db.query(IntentReviewLog).filter(IntentReviewLog.is_reviewed == is_reviewed)
    total = query.count()
    
    # 🌟 新增：抓取最舊的一筆紀錄時間
    oldest_log = query.order_by(IntentReviewLog.created_at.asc()).first()
    oldest_date = oldest_log.created_at.strftime("%Y-%m-%d %H:%M:%S") if oldest_log and oldest_log.created_at else None
    
    logs = query.order_by(IntentReviewLog.created_at.desc()).offset((page-1)*size).limit(size).all()
    details = []
    for l in logs:
        details.append({
            "review_id": l.review_id,
            "user_message": l.user_message,
            "llm_response": l.llm_response,
            "predicted_intent": l.predicted_intent,
            "confidence_score": float(l.confidence_score),
            "corrected_intent": l.corrected_intent or l.predicted_intent,
            "created_at": l.created_at.strftime("%Y-%m-%d %H:%M:%S") if l.created_at else None
        })
    # 🌟 把 oldest_date 一起丟給前端
    return {"total": total, "details": details, "oldest_date": oldest_date}



@router.post("/feedback", summary="👤 用戶主動回饋 (倒讚)")
async def user_feedback(
    payload: dict = Body(...), 
    db: Session = Depends(get_db), 
    current_user: Member = Depends(get_current_user)
):
    """接收來自前端 Vue 的 👎 倒讚回饋"""
    user_msg = payload.get("user_message", "未知問題")
    llm_res = payload.get("llm_response", "")
    pred_intent = payload.get("predicted_intent", "UNKNOWN")
    conf_score = payload.get("confidence_score", 0.0)

    new_log = IntentReviewLog(
        user_id=current_user.user_id,
        user_message=user_msg,
        predicted_intent=pred_intent,
        confidence_score=Decimal(str(conf_score)),
        llm_response=llm_res,
        is_reviewed=0 # 標記為未審核，讓它出現在你的 pending 列表
    )
    db.add(new_log)
    db.commit()
    return {"success": True, "message": "反饋已記錄喵！"}

@router.delete("/logs/cleanup", summary="🧹 清理過期審核紀錄")
async def cleanup_old_logs(db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)):
    """一鍵清理超過 30 天且未審核的無效紀錄，避免資料庫爆炸"""
    if current_user.role not in ["admin"]: 
        raise HTTPException(status_code=403, detail="權限不足")
        
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    # 刪除條件：未審核 (0) 且 建立時間大於 30 天
    deleted_count = db.query(IntentReviewLog).filter(
        IntentReviewLog.is_reviewed == 0,
        IntentReviewLog.created_at < thirty_days_ago
    ).delete()
    
    db.commit()
    return {"success": True, "message": f"成功清理 {deleted_count} 筆過期紀錄喵！"}

@router.delete("/logs/clear_all_pending", summary="💣 一鍵清空所有未審核紀錄")
async def clear_all_pending_logs(db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)):
    """大掃除專用：無條件刪除所有 is_reviewed == 0 的紀錄"""
    if current_user.role not in ["admin"]: 
        raise HTTPException(status_code=403, detail="權限不足")
        
    # 刪除條件：只要是未審核 (0) 的通通殺掉
    deleted_count = db.query(IntentReviewLog).filter(IntentReviewLog.is_reviewed == 0).delete()
    db.commit()
    
    return {"success": True, "message": f"太爽了！已成功清空 {deleted_count} 筆歷史髒資料喵！"}


@router.post("/batch_run", summary="🏃 執行三方批次測試")
async def batch_test_ai(db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)):
    if current_user.role not in ["ai_test", "admin"]: raise HTTPException(status_code=403, detail="權限不足")
    
    # 自動尋找目前上傳的是哪種格式的檔案
    file_path = None
    if os.path.exists(CURRENT_BATCH_FILE_BASE + ".xlsx"): file_path = CURRENT_BATCH_FILE_BASE + ".xlsx"
    elif os.path.exists(CURRENT_BATCH_FILE_BASE + ".csv"): file_path = CURRENT_BATCH_FILE_BASE + ".csv"
    else: file_path = DEFAULT_TEST_FILE

    if not os.path.exists(file_path): raise HTTPException(status_code=404, detail="找不到測試集！")
    
    try:
        results, v1_acc, v2_acc, count = [], 0.0, 0.0, 0
        
        if file_path.endswith('.csv'):
            # 🌟 防呆 1：解決台灣 Excel 匯出 CSV 變成 Big5 編碼導致崩潰的問題
            encoding_to_use = 'utf-8-sig'
            try:
                with open(file_path, 'r', encoding='utf-8-sig') as f:
                    f.read()
            except UnicodeDecodeError:
                encoding_to_use = 'big5' # 若 UTF-8 解析失敗，自動切換為 Big5

            with open(file_path, newline='', encoding=encoding_to_use) as f:
                reader = csv.DictReader(f)
                
                # 🌟 防呆 2：清理標題列的空白或不可見字元 (BOM)
                fieldnames = [str(col).strip() for col in (reader.fieldnames or [])]
                
                if 'text' not in fieldnames or 'intent' not in fieldnames:
                    raise HTTPException(status_code=400, detail=f"CSV 必須包含 'text' 和 'intent' 標題列喵！目前抓到的是: {fieldnames}")
                
                for row in reader:
                    # 字典取值時也確保欄位名稱對齊
                    row_cleaned = {str(k).strip(): v for k, v in row.items()}
                    msg = str(row_cleaned.get('text', '')).strip()
                    true_i = str(row_cleaned.get('intent', '')).strip()
                    if not msg: continue
                    
                    v1_p, _ = arena_brains.predict_v1(msg)
                    v2_p, _, v2_int = arena_brains.predict_v2(msg)
                    
                    v1_s, v2_s = calculate_score(true_i, v1_p), calculate_score(true_i, v2_p)
                    v1_acc += v1_s; v2_acc += v2_s; count += 1
                    
                    results.append({"text": msg, "true_intent": true_i, "v1_pred": v1_p, "v2_pred": v2_p, "v2_score": v2_s, "v2_is_intercepted": v2_int})

        else:
            wb = openpyxl.load_workbook(file_path, data_only=True)
            sheet = wb.active
            if sheet is None:
                raise HTTPException(status_code=500, detail="Excel 檔案沒有有效的工作表喵！")
                
            # 🌟 防呆 3：Excel 標題列同樣清理乾淨
            headers = [str(cell.value).strip() if cell.value else "" for cell in sheet[1]]
            if 'text' not in headers or 'intent' not in headers:
                raise HTTPException(status_code=400, detail="Excel 必須包含 'text' 和 'intent' 標題列喵！")
                
            t_idx, i_idx = headers.index('text'), headers.index('intent')
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if not row[t_idx]: continue
                msg, true_i = str(row[t_idx]).strip(), str(row[i_idx]).strip()
                
                v1_p, _ = arena_brains.predict_v1(msg)
                v2_p, _, v2_int = arena_brains.predict_v2(msg)
                
                v1_s, v2_s = calculate_score(true_i, v1_p), calculate_score(true_i, v2_p)
                v1_acc += v1_s; v2_acc += v2_s; count += 1
                
                results.append({"text": msg, "true_intent": true_i, "v1_pred": v1_p, "v2_pred": v2_p, "v2_score": v2_s, "v2_is_intercepted": v2_int})
                
        db.commit()
        if count == 0: count = 1 # 防呆避免除以 0
        return {"success": True, "v1_accuracy": v1_acc/count, "v2_accuracy": v2_acc/count, "details": results, "total": count}
        
    except HTTPException:
        # 🌟 關鍵修復：如果已經是我們自己拋出的 400 錯誤，就讓它正常通過，不要被包裝成 500
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"解析失敗喵：{str(e)}")
    
    
    
    
@router.post("/compare", summary="🎙️ 手動三強單句對比")
async def compare_ai_intent(message: str = Body(..., embed=True), db: Session = Depends(get_db), current_user: Member = Depends(get_current_user)):
    if current_user.role not in ["ai_test", "admin"]: raise HTTPException(status_code=403, detail="權限不足")
    if is_malicious(message): return {"legacy": {"intent": "BLOCKED"}}

    legacy_i = FinanceAgentService.analyze_intent(message)
    v1_i, v1_c = arena_brains.predict_v1(message)
    v2_i, v2_c, v2_int = arena_brains.predict_v2(message)

    new_log = IntentReviewLog(user_id=current_user.user_id, user_message=message, predicted_intent=v2_i, confidence_score=Decimal(str(v2_c)))
    db.add(new_log); db.commit(); db.refresh(new_log)

    # 🌟 這裡呼叫剛補回來的 get_reply
    legacy_res, v2_res = await asyncio.gather(
        get_reply(db, current_user, message, legacy_i),
        get_reply(db, current_user, message, v2_i)
    )

    return {
        "review_id": new_log.review_id,
        "legacy": {"intent": legacy_i, "response": legacy_res},
        "v1_ai": {"intent": v1_i, "confidence": v1_c},
        "v2_ai": {"intent": v2_i, "confidence": v2_c, "is_intercepted": v2_int, "response": v2_res}
    }

@router.put("/logs/{review_id}", summary="🛠️ 更新修正結果")
async def update_intent_review(
    review_id: int, 
    payload: dict = Body(...), 
    db: Session = Depends(get_db), 
    current_user: Member = Depends(get_current_user)
):
    if current_user.role not in ["ai_test", "admin"]: 
        raise HTTPException(status_code=403, detail="權限不足")
        
    log = db.query(IntentReviewLog).filter(IntentReviewLog.review_id == review_id).first()
    if not log: 
        raise HTTPException(status_code=404, detail="找不到紀錄")
        
    corrected = payload.get("corrected_intent")
    
    if corrected:
        log.corrected_intent = corrected
        log.is_reviewed = 1
        
        # 🌟 判斷：如果是「真正需要糾正」的錯誤，才寫入 ChromaDB 進行學習
        if corrected != log.predicted_intent:
            if arena_brains.chroma_store:
                arena_brains.chroma_store.add_documents([
                    Document(page_content=log.user_message, metadata={"intent": corrected})
                ])
                logger.info(f"🧠 已將糾正語句寫入 ChromaDB: {log.user_message} -> {corrected}")
        
        db.commit()
        return {"success": True}
        
    raise HTTPException(status_code=400, detail="無效意圖")


@router.delete("/logs/{review_id}", summary="🗑️ 刪除單筆審核紀錄")
async def delete_intent_review(
    review_id: int, 
    db: Session = Depends(get_db), 
    current_user: Member = Depends(get_current_user)
):
    if current_user.role not in ["ai_test", "admin"]: 
        raise HTTPException(status_code=403, detail="權限不足")
        
    log = db.query(IntentReviewLog).filter(IntentReviewLog.review_id == review_id).first()
    if not log: 
        raise HTTPException(status_code=404, detail="找不到紀錄")
        
    db.delete(log)
    db.commit()
    return {"success": True, "message": "紀錄已成功刪除喵！"}


# 新增「工程師直通車」API (ai_cat_test.py)
from pydantic import BaseModel
class EngineerCorrection(BaseModel):
    user_message: str
    predicted_intent: str
    corrected_intent: str
    confidence_score: float = 1.0
@router.post("/logs/engineer_fix", summary="🛠️ 工程師專用：直接修正並雙重入庫")
async def engineer_direct_fix(
    payload: EngineerCorrection,
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user)
):
    """供 QA 測試頁面批次除錯使用，一次完成 MySQL 留底 + ChromaDB 訓練"""
    if current_user.role not in ["ai_test", "admin"]: 
        raise HTTPException(status_code=403, detail="權限不足")
        
    # 1. 寫入 MySQL 留底 (直接標記為 is_reviewed=1 已解決)
    new_log = IntentReviewLog(
        user_id=current_user.user_id,
        user_message=payload.user_message,
        predicted_intent=payload.predicted_intent,
        corrected_intent=payload.corrected_intent,
        confidence_score=Decimal(str(payload.confidence_score)),
        llm_response="[工程師測試台批次快速修正]", # 標記來源
        is_reviewed=1 
    )
    db.add(new_log)
    
    # 2. 寫入 ChromaDB 大腦
    if arena_brains.chroma_store:
        arena_brains.chroma_store.add_documents([
            Document(page_content=payload.user_message, metadata={"intent": payload.corrected_intent})
        ])
        logger.info(f"🧠 [工程師手動注入] ChromaDB: {payload.user_message} -> {payload.corrected_intent}")
        
    db.commit()
    return {"success": True, "message": "雙重入庫成功！"}

# routes/ai/ai_speech_correction.py
import time
import os
import gc
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ...database import get_db
from ...models import ASRCorrectionLog,Member
from ...dependencies import admin_required, get_current_user
from ...schemas.speech import CorrectionRequest, CorrectionResponse, ToggleRequest


# 偵測是否在本地環境 (可以自己在 .env 裡設定 USE_LOCAL_GPU=True)
USE_LOCAL_GPU = os.getenv("USE_LOCAL_GPU", "False").lower() == "true"


router = APIRouter()

class QwenLoRAModel:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(QwenLoRAModel, cls).__new__(cls)
            cls._instance.is_loaded = False
            cls._instance.model = None
            cls._instance.tokenizer = None
        return cls._instance

    def load_model(self):
        if self.is_loaded:
            return True
            
        print("⏳ [GPU] 正在喚醒沉睡的 AI 套件與模型權重...")
        
        try:
            # 🌟 真・延遲載入：只有按下啟用時，才將這些肥大套件載入記憶體
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
            from peft import PeftModel

            base_model_id = "Qwen/Qwen2.5-1.5B-Instruct"
            lora_path = os.path.join(os.getcwd(), "web_app", "models", "qwen_lora_new") 

            self.tokenizer = AutoTokenizer.from_pretrained(base_model_id)
            
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16
            )

            base_model = AutoModelForCausalLM.from_pretrained(
                base_model_id,
                quantization_config=bnb_config,
                device_map="auto"
            )

            self.model = PeftModel.from_pretrained(base_model, lora_path)
            self.model.eval()
            self.is_loaded = True
            print("✅ 財經糾錯 QLoRA 模型已成功掛載至顯卡！")
            return True
            
        except Exception as e:
            print(f"❌ 模型載入失敗: {e}")
            return False

    def unload_model(self):
        """將模型從 VRAM 中徹底清空"""
        if not self.is_loaded:
            return
        print("🧹 正在將模型從 GPU 記憶體中卸載...")
        
        # 刪除變數參考
        self.model = None
        self.tokenizer = None
        
        # 強制 Python 回收垃圾
        gc.collect()
        
        # 延遲載入 torch 以清空 CUDA 緩存
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
            
        self.is_loaded = False
        print("✅ GPU 記憶體已完美釋放！")

    def correct_text(self, raw_text: str):
        # 修復 Pylance 警告：明確告訴 Pylance 如果模型沒載入就直接 return
        if not self.is_loaded or self.tokenizer is None or self.model is None:
            return raw_text 
            
        import torch # 推論時需要用到 torch.no_grad()
            
        prompt = f"<|im_start|>system\n請修正語音辨識錯誤<|im_end|>\n<|im_start|>user\n{raw_text}<|im_end|>\n<|im_start|>assistant\n"
        
        # 這裡 Pylance 就不會報錯了，因為上面已經排除了 None 的可能
        inputs = self.tokenizer(prompt, return_tensors="pt").to("cuda")
        
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=100,
                temperature=0.1,
                pad_token_id=self.tokenizer.eos_token_id,
                eos_token_id=self.tokenizer.eos_token_id
            )
            
        decoded_output = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        try:
            return decoded_output.split("assistant\n")[-1].strip()
        except:
            return decoded_output.strip()

# 伺服器啟動時，這裡「完全不會」吃掉任何顯卡記憶體
print("🚀 初始化 AI 糾錯服務 (預設為輕量休眠模式)...")
ai_model = QwenLoRAModel()

# ==========================================
# 🛡️ 權限控制 API 路由區
# ==========================================

# 1. 取得狀態：僅限管理員
@router.get("/status")
def get_ai_status(admin: Member = Depends(admin_required)):
    return {"is_enabled": ai_model.is_loaded}

# 2. 開關 AI 模型：僅限管理員
@router.post("/toggle")
def toggle_ai_model(req: ToggleRequest, admin: Member = Depends(admin_required)):
    if req.enable:
        success = ai_model.load_model()
        if not success:
            raise HTTPException(status_code=500, detail="模型載入失敗，請檢查後端 Log")
        return {"message": "模型已成功載入 GPU", "is_enabled": True}
    else:
        ai_model.unload_model()
        return {"message": "模型已從 GPU 卸載", "is_enabled": False}

# 3. 語音糾錯處理：一般登入會員即可使用
@router.post("/process", response_model=CorrectionResponse)
def process_speech_correction(
    request: CorrectionRequest, 
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user) # 🌟 抓取當下發送請求的真實使用者
):
    raw_text = request.raw_text.strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="請輸入原始辨識文字")

    start_time = time.time()
    
    if not ai_model.is_loaded:
        corrected_text = raw_text
    else:
        try:
            corrected_text = ai_model.correct_text(raw_text)
        except Exception as e:
            print(f"❌ 模型推論發生錯誤: {e}")
            corrected_text = raw_text
            
    inference_time_ms = int((time.time() - start_time) * 1000)

    # 🌟 將寫死的 1 改為真正使用者的 user_id
    new_log = ASRCorrectionLog(
        user_id=current_user.user_id, 
        raw_asr_text=raw_text,
        corrected_text=corrected_text,
        inference_time_ms=inference_time_ms
    )
    db.add(new_log)
    db.commit()
    db.refresh(new_log)

    return CorrectionResponse(
        log_id=new_log.log_id,
        raw_text=raw_text,
        corrected_text=corrected_text,
        inference_time_ms=inference_time_ms
    )
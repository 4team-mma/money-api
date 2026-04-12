import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

class ASRCorrectionService:
    def __init__(self):
        print("⏳ 正在啟動 Qwen2.5 財經糾錯大腦...")
        
        # 1. 指定基底模型 (第一次跑會在背景自動從 Hugging Face 下載到本機快取)
        base_model_id = "Qwen/Qwen2.5-1.5B-Instruct"
        
        # 2. 指定你剛剛放進專案裡的 LoRA 外掛路徑
        lora_path = "./models/qwen_lora_final"
        
        # 3. 載入 Tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(base_model_id)
        
        # 4. 載入基底模型 (使用 4060 Ti 的 CUDA 和 Float16)
        base_model = AutoModelForCausalLM.from_pretrained(
            base_model_id,
            device_map="cuda",          # 🌟 直接丟給 4060 Ti 處理
            torch_dtype=torch.float16,  # 🌟 節省顯存，跑得更快
        )
        
        # 5. 🌟 終極合體：把外掛裝上大腦！
        self.model = PeftModel.from_pretrained(base_model, lora_path)
        self.model.eval() # 切換成推論模式
        
        print("✅ 財經糾錯大腦啟動完畢！")

    def correct_text(self, error_text: str) -> str:
        # 使用 Qwen 專屬的 ChatML 格式
        prompt = f"<|im_start|>system\n你是一個財經語音糾錯助手。請將以下語音辨識草稿修正為正確的記帳文字，僅修正錯別字，切勿改變原本的語氣與句型。<|im_end|>\n<|im_start|>user\n{error_text}<|im_end|>\n<|im_start|>assistant\n"
        
        inputs = self.tokenizer(prompt, return_tensors="pt").to("cuda")
        
        # 讓模型生成答案
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs, 
                max_new_tokens=50, 
                temperature=0.1, 
                pad_token_id=self.tokenizer.eos_token_id
            )
            
        # 解碼並只回傳 assistant 的回答部分
        response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        return response.split('assistant')[-1].strip()

# --- 測試看看 ---
# if __name__ == "__main__":
#     service = ASRCorrectionService()
#     result = service.correct_text("幫我寄一筆，今天去全聯刷了溜溜卡，買菜花了一千二。")
#     print(f"修正結果: {result}")
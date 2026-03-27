# python groq_data_generator.py
import customtkinter as ctk
import requests
import pandas as pd
import threading
import os
import glob
import sys
import tkinter.filedialog as fd
from dotenv import load_dotenv
from groq import Groq
import groq

# 嘗試讀取專案底下的 .env 檔案，看有沒有存 GROQ_API_KEY
load_dotenv()

# 🎨 系統外觀設定
ctk.set_appearance_mode("Dark")  
ctk.set_default_color_theme("green") # 換成綠色主題，跟 Ollama 的藍色做區分！

class GroqDataGeneratorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("白白AI資料生成器 (極速版)")
        self.geometry("750x800")
        
        # --- UI 介面佈局 ---
        self.title_label = ctk.CTkLabel(self, text="😺MMA雲端資料生成器", font=("Arial", 24, "bold"))
        self.title_label.pack(pady=15)
        
        # 🔑 金鑰設定區
        self.key_frame = ctk.CTkFrame(self)
        self.key_frame.pack(pady=5, padx=20, fill="x")
        ctk.CTkLabel(self.key_frame, text="Groq API Key:").pack(side="left", padx=10, pady=10)
        self.api_key_entry = ctk.CTkEntry(self.key_frame, width=400, show="*", placeholder_text="請貼上你的 GROQ_API_KEY (gsk_...)")
        
        env_key = os.getenv("GROQ_API_KEY", "")
        if env_key:
            self.api_key_entry.insert(0, env_key)
        self.api_key_entry.pack(side="left", padx=10)

        # 🧠 模型設定區
        self.model_frame = ctk.CTkFrame(self)
        self.model_frame.pack(pady=5, padx=20, fill="x")
        ctk.CTkLabel(self.model_frame, text="雲端 Groq 模型:").pack(side="left", padx=10, pady=10)
        
        # 🌟 模型名稱對應字典
        self.model_mapping = {
            "Llama 3.3 70B (穩定主力/假資料神機)": "llama-3.3-70b-versatile",
            "Llama 3.1 8B (極速生成/輕量首選)": "llama-3.1-8b-instant", 
            "Llama 4 Scout (最新視覺/多模態/日常)": "meta-llama/llama-4-scout-17b-16e-instruct",
            "GPT OSS 120B (超強推理/複雜邏輯)": "openai/gpt-oss-120b",
            "GPT OSS 20B (輕量推理/速度快)": "openai/gpt-oss-20b",
            "Qwen 3 32B (強大開源/程式與生成)": "qwen/qwen3-32b"
        }
        
        self.model_combo = ctk.CTkComboBox(self.model_frame, values=list(self.model_mapping.keys()), width=300)
        self.model_combo.set("Llama 3.3 70B (穩定主力/假資料神機)")
        self.model_combo.pack(side="left", padx=10)
        
        # 模式切換開關
        self.mode_switch = ctk.CTkSwitch(self.model_frame, text="開啟 MySQL 假資料模式", command=self.toggle_mode)
        self.mode_switch.pack(side="right", padx=20)

        # 意圖/資料表選擇與數量
        self.setting_frame = ctk.CTkFrame(self)
        self.setting_frame.pack(pady=10, padx=20, fill="x")
        
        self.intent_label = ctk.CTkLabel(self.setting_frame, text="生成類別:")
        self.intent_label.grid(row=0, column=0, padx=10, pady=10)
        
        self.nlp_options = ["RECORD (記帳)", "QUERY (查詢)", "CHAT (閒聊)", "ADVISOR (顧問)", "KNOWLEDGE (手冊)"]
        self.mysql_options = ["adds (帳單紀錄)", "budgets (預算設定)", "savings_goals (儲蓄目標)", "accounts (我的帳戶)", "transactions (轉帳紀錄)", "feedbacks (意見回饋)"]
        
        self.intent_combo = ctk.CTkComboBox(self.setting_frame, values=self.nlp_options, width=180)
        self.intent_combo.grid(row=0, column=1, padx=5, pady=10)
        
        # 🌟 上傳按鈕
        self.upload_btn = ctk.CTkButton(self.setting_frame, text="📁 上傳自訂表", command=self.upload_schema, fg_color="gray", state="disabled", width=120)
        self.upload_btn.grid(row=0, column=2, padx=5, pady=10)
        
        # 🌟 恢復預設按鈕
        self.reset_btn = ctk.CTkButton(self.setting_frame, text="🔄 恢復預設", command=self.reset_schema, fg_color="gray", state="disabled", width=100)
        self.reset_btn.grid(row=0, column=3, padx=5, pady=10)
        
        self.custom_schema_content = "" 
        self.custom_table_name = ""     
        
        ctk.CTkLabel(self.setting_frame, text="生成數量:").grid(row=1, column=0, padx=10, pady=10)
        self.count_entry = ctk.CTkEntry(self.setting_frame, width=80)
        self.count_entry.insert(0, "30") 
        self.count_entry.grid(row=1, column=1, padx=10, pady=10)
        
        # Log 顯示區
        self.log_box = ctk.CTkTextbox(self, height=300, font=("Arial", 14))
        self.log_box.pack(pady=10, padx=20, fill="both", expand=True)
        
        # 按鈕區
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(pady=10)
        self.start_btn = ctk.CTkButton(self.btn_frame, text="🚀 雲端極速生成", command=self.start_generation_thread)
        self.start_btn.pack(side="left", padx=10)
        
        self.generated_data = []
        self.is_mysql_mode = False

    def toggle_mode(self):
        self.log_box.delete("1.0", "end") 
        self.is_mysql_mode = self.mode_switch.get() == 1
        
        if self.is_mysql_mode:
            self.intent_combo.configure(values=self.mysql_options)
            self.intent_combo.set(self.mysql_options[0])
            self.upload_btn.configure(state="normal", fg_color="#1f538d")
            self.log("🔄 已切換為【MySQL 假資料模式】！(支援上傳自訂表結構)")
        else:
            self.intent_combo.configure(values=self.nlp_options)
            self.intent_combo.set(self.nlp_options[0])
            self.upload_btn.configure(state="disabled", fg_color="gray")
            self.reset_btn.configure(state="disabled", fg_color="gray")
            self.custom_schema_content = "" 
            self.log("🔄 已切換為【Keras 意圖訓練模式】！")

    def upload_schema(self):
        path = fd.askopenfilename(filetypes=[("SQL or Text Files", "*.sql *.txt")])
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    self.custom_schema_content = f.read()
                
                self.custom_table_name = os.path.basename(path).split('.')[0]
                
                new_option = f"自訂表: {self.custom_table_name}"
                current_values = list(self.intent_combo.cget("values"))
                if new_option not in current_values:
                    current_values.insert(0, new_option)
                
                self.intent_combo.configure(values=current_values)
                self.intent_combo.set(new_option)
                
                self.reset_btn.configure(state="normal", fg_color="#d63a3a") 
                self.log(f"📁 成功載入自訂表結構 [{self.custom_table_name}]！別的組也能開心產資料啦。")
            except Exception as e:
                self.log(f"❌ 讀取檔案失敗: {str(e)}")

    def reset_schema(self):
        self.custom_schema_content = ""
        self.custom_table_name = ""
        
        self.intent_combo.configure(values=self.mysql_options)
        self.intent_combo.set(self.mysql_options[0])
        self.reset_btn.configure(state="disabled", fg_color="gray")
        self.log("🔄 已清除別人上傳的表結構，恢復為本組專用的預設資料表！")

    def log(self, message):
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")

    def get_next_filename(self, base_name, extension):
        # 🌟 打包路徑魔法
        if getattr(sys, 'frozen', False):
            if sys.platform == 'darwin' and '.app' in sys.executable:
                base_dir = os.path.abspath(os.path.join(os.path.dirname(sys.executable), '../../..'))
            else:
                base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        save_dir = os.path.join(base_dir, "ai_training", "dataset")
        os.makedirs(save_dir, exist_ok=True)
        
        pattern = os.path.join(save_dir, f"{base_name}_*.{extension}")
        existing_files = glob.glob(pattern)
        
        if not existing_files:
            return os.path.join(save_dir, f"{base_name}_001.{extension}")
            
        max_num = 0
        for f in existing_files:
            try:
                num_str = f.split('_')[-1].split('.')[0]
                max_num = max(max_num, int(num_str))
            except ValueError:
                continue
        next_num = max_num + 1
        return os.path.join(save_dir, f"{base_name}_{next_num:03d}.{extension}")

    def start_generation_thread(self):
        api_key = self.api_key_entry.get().strip()
        if not api_key:
            self.log("❌ 錯誤：請先輸入 Groq API Key！")
            return
            
        self.start_btn.configure(state="disabled", text="⏳ 雲端運算中...")
        self.generated_data = []
        threading.Thread(target=self.generate_data, args=(api_key,)).start()

    def generate_data(self, api_key):
        display_model_name = self.model_combo.get()
        model_name = self.model_mapping.get(display_model_name, "llama-3.3-70b-versatile")
        count = int(self.count_entry.get())
        selected_option = self.intent_combo.get().split(" ")[0] 
        
        if self.is_mysql_mode:
            self.log(f"🔥 連線 Groq ({model_name}) 生成 {count} 筆 SQL...")
            
            # 🌟 自訂表邏輯
            if selected_option.startswith("自訂表:"):
                selected_option = self.custom_table_name 
                prompt = f"請根據以下的資料表結構，生成 {count} 筆符合格式的 MySQL INSERT 語法。\n盡量讓資料看起來真實且多樣化。\n純SQL輸出，每行一條，嚴禁任何 markdown 標籤或解說。\n表結構如下：\n{self.custom_schema_content}"
            elif selected_option == "adds":
                prompt = f"生成 {count} 筆 MySQL INSERT 語法新增至 `adds` 表。\n規則: user_id(1), account_id(1), add_date(2025-10-01到2026-03-31), add_type=1(收入,類別:工資/獎金/投資, icon:💰/🏦/🐷), add_type=0(支出,類別:飲食/交通/居家/娛樂, icon:🍔/🚗/🏠/🎮), add_member(自己/父母/孩子), add_tag(需要/想要/旅遊), add_amount(50~5000), add_note(具體項目10字內)。\n純SQL輸出每行一條，嚴禁markdown。"
            elif selected_option == "accounts":
                prompt = f"生成 {count} 筆 INSERT 語法至 `accounts` 表。\n欄位: user_id(1), account_type('cash'或'bank'), account_name(如:國泰世華), currency('NT$'), initial_balance(1000~50000), current_balance(同 initial_balance), exclude_from_assets(0或1), account_icon(💳 或 🏦)。\n純SQL輸出每行一條。"
            elif selected_option == "feedbacks":
                prompt = f"生成 {count} 筆 INSERT 語法至 `feedbacks` 表。\n欄位: user_id(1), feedback_name(如:王小明), question_type(系統Bug/功能建議), use_page(首頁/記帳頁), content(模擬抱怨或建議20字內)。\n純SQL輸出每行一條。"
            else: 
                prompt = f"生成 {count} 筆 INSERT INTO 語法，新增至 `{selected_option}` 表。user_id 皆填 1。純SQL輸出每行一條。"
        else:
            intent = selected_option
            self.log(f"🔥 連線 Groq ({model_name}) 生成 {count} 筆 `{intent}` NLP 訓練句子...")
            prompt_templates = {
                "RECORD": f"生成 {count} 句台灣人「記帳」的口語說法。必須包含金額和項目。例如：午餐100元。直接列表輸出，一行一句。",
                "QUERY": f"生成 {count} 句台灣人「查帳、問預算、問餘額」的口語說法。直接列表輸出，一行一句。",
                "CHAT": f"生成 {count} 句跟理財助手「閒聊、無意義」的說法。直接列表輸出，一行一句。",
                "ADVISOR": f"生成 {count} 句向理財顧問「尋求建議、評估消費」的說法。直接列表輸出，一行一句。",
                "KNOWLEDGE": f"生成 {count} 句詢問「系統操作、成就解鎖規則」的說法。直接列表輸出，一行一句。"
            }
            prompt = prompt_templates[intent]
        
        try:
            client = Groq(api_key=api_key)
            response = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=model_name,
                temperature=0.7,
            )
            
            content = response.choices[0].message.content
            result_text = content.strip() if content else ""
                
            if "```sql" in result_text: 
                result_text = result_text.split("```sql")[1].split("```")[0].strip()
            elif "```" in result_text: 
                result_text = result_text.split("```")[1].strip()

            lines = result_text.split('\n')
            success_count = 0
            for line in lines:
                clean_line = line.strip("1234567890.、- *\"'")
                if len(clean_line) > 10 if self.is_mysql_mode else len(clean_line) > 2:
                    if self.is_mysql_mode:
                        self.generated_data.append(line.strip())
                    else:
                        self.generated_data.append({"text": clean_line, "intent": selected_option})
                    
                    if success_count < 5: 
                        self.log(f"✔️ {clean_line[:60]}...")
                    success_count += 1
            
            self.log(f"\n✅ 成功獲取 {success_count} 筆資料！(Groq 官方通道連線成功！)")
            self.save_to_file(selected_option)

        except groq.AuthenticationError:
            self.log("❌ 錯誤：Groq 官方驗證失敗 (401)！請確認金鑰是否過期或被官方停用。")
        except Exception as e:
            self.log(f"❌ 連線失敗！\n錯誤原因：{e}\n建議：請檢查網路或稍後再試。")
            
        finally:
            self.start_btn.configure(state="normal", text="🚀 雲端極速生成")

    def save_to_file(self, base_name):
        if not self.generated_data: return
        
        if self.is_mysql_mode:
            filename = self.get_next_filename(f"{base_name}_mock", "sql")
            with open(filename, 'w', encoding='utf-8') as f:
                for sql_line in self.generated_data:
                    f.write(sql_line + "\n")
            self.log(f"💾 SQL 語法已成功儲存至: {filename}")
            
        else:
            filename = self.get_next_filename(base_name, "xlsx")
            df = pd.DataFrame(self.generated_data)
            try:
                df.to_excel(filename, index=False)
                self.log(f"💾 NLP 訓練集已成功儲存至: {filename}")
            except PermissionError:
                self.log(f"❌ 儲存失敗！請確保 {filename} 沒有在 Excel 中開啟。")

if __name__ == "__main__":
    app = GroqDataGeneratorApp()  
    app.mainloop()
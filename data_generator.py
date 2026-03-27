# 地端使用/需要 Ollama 開啟狀態下使用
# python data_generator.py
import customtkinter as ctk
import requests
import pandas as pd
import threading
import os
import glob
import sys
import tkinter.filedialog as fd
import json

# 🎨 系統外觀設定
ctk.set_appearance_mode("Dark")  
ctk.set_default_color_theme("blue") # 藍色主題，與雲端 Groq 的綠色做區分

class DataGeneratorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("白白AI資料生成器 (地端 Ollama 豪華版)")
        self.geometry("850x850") # 稍微加寬介面
        
        # --- UI 介面佈局 ---
        self.title_label = ctk.CTkLabel(self, text="🤖 Ollama 地端資料生成器", font=("Arial", 24, "bold"))
        self.title_label.pack(pady=15)
        
        # 🧠 模型設定區
        self.model_frame = ctk.CTkFrame(self)
        self.model_frame.pack(pady=5, padx=20, fill="x")
        ctk.CTkLabel(self.model_frame, text="本地 Ollama 模型:").pack(side="left", padx=10, pady=10)
        
        # 🌟 新增：地端模型名稱對應字典 (UI顯示名稱 : Ollama 實際 ID)
        # 根據你的配備 (RTX 3050 6GB)，7B/8B 是最適合的模型大小
        self.model_mapping = {
            "Llama 3.1 8B (綜合性能最強/台灣口語好)": "llama3.1",
            "DeepSeek R1 8B (最強推理思維/複雜 SQL)": "deepseek-r1:8b",
            "Gemma 2 9B (Google出品/邏輯嚴謹/稍慢)": "gemma2",
            "Llama 3.2 3B (極速生成/輕量首選)": "llama3.2",
            "Gemma 3 4B (小巧聰明/適合日常邏輯)": "gemma3:4b",
            "Gemma 3 1B (極度輕量/幾乎不佔資源)": "gemma3:1b"
        }
        
        # UI 下拉選單只顯示「中文註解」
        self.model_combo = ctk.CTkComboBox(self.model_frame, values=list(self.model_mapping.keys()), width=350)
        self.model_combo.set("Llama 3.1 8B (綜合性能最強/台灣口語好)") # 預設設定
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
        
        # 🌟 上傳按鈕 (移植雲端版功能)
        self.upload_btn = ctk.CTkButton(self.setting_frame, text="📁 上傳自訂表", command=self.upload_schema, fg_color="gray", state="disabled", width=120)
        self.upload_btn.grid(row=0, column=2, padx=5, pady=10)
        
        # 🌟 恢復預設按鈕 (移植雲端版功能)
        self.reset_btn = ctk.CTkButton(self.setting_frame, text="🔄 恢復預設", command=self.reset_schema, fg_color="gray", state="disabled", width=100)
        self.reset_btn.grid(row=0, column=3, padx=5, pady=10)
        
        self.custom_schema_content = "" # 存放讀取到的表結構
        self.custom_table_name = ""     # 存放表名稱
        
        ctk.CTkLabel(self.setting_frame, text="生成數量:").grid(row=1, column=0, padx=10, pady=10)
        self.count_entry = ctk.CTkEntry(self.setting_frame, width=80)
        self.count_entry.insert(0, "10") # 地端較慢，預設 10 筆
        self.count_entry.grid(row=1, column=1, padx=10, pady=10)
        
        # Log 顯示區
        self.log_box = ctk.CTkTextbox(self, height=300, font=("Arial", 14))
        self.log_box.pack(pady=10, padx=20, fill="both", expand=True)
        
        # 按鈕區
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(pady=10)
        self.start_btn = ctk.CTkButton(self.btn_frame, text="🚀 地端加速生成", command=self.start_generation_thread)
        self.start_btn.pack(side="left", padx=10)
        
        self.generated_data = []
        self.is_mysql_mode = False

    def toggle_mode(self):
        self.log_box.delete("1.0", "end") 
        self.is_mysql_mode = self.mode_switch.get() == 1
        
        if self.is_mysql_mode:
            self.intent_combo.configure(values=self.mysql_options)
            self.intent_combo.set(self.mysql_options[0])
            self.upload_btn.configure(state="normal", fg_color="#1f538d") # 藍色按鈕
            self.log("🔄 已切換為【MySQL 假資料模式】！(支援地端讀取自訂表結構)")
        else:
            self.intent_combo.configure(values=self.nlp_options)
            self.intent_combo.set(self.nlp_options[0])
            self.upload_btn.configure(state="disabled", fg_color="gray")
            self.reset_btn.configure(state="disabled", fg_color="gray")
            self.custom_schema_content = "" 
            self.log("🔄 已切換為【Keras 意圖訓練模式】！")

    # 🌟 處理上傳檔案 (地端通用化)
    def upload_schema(self):
        path = fd.askopenfilename(filetypes=[("SQL or Text Files", "*.sql *.txt")])
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    self.custom_schema_content = f.read()
                
                self.custom_table_name = os.path.basename(path).split('.')[0]
                
                # 在下拉選單最前面加入自訂表
                new_option = f"自訂表: {self.custom_table_name}"
                current_values = list(self.intent_combo.cget("values"))
                if new_option not in current_values:
                    current_values.insert(0, new_option)
                
                self.intent_combo.configure(values=current_values)
                self.intent_combo.set(new_option)
                
                # 啟用恢復預設按鈕
                self.reset_btn.configure(state="normal", fg_color="#d63a3a") # 紅色按鈕
                self.log(f"📁 成功載入地端表結構 [{self.custom_table_name}]！別組的 .sql 也能本地產資料了。")
            except Exception as e:
                self.log(f"❌ 讀取檔案失敗: {str(e)}")

    # 🌟 一鍵恢復成預設狀態
    def reset_schema(self):
        self.custom_schema_content = ""
        self.custom_table_name = ""
        
        self.intent_combo.configure(values=self.mysql_options)
        self.intent_combo.set(self.mysql_options[0])
        self.reset_btn.configure(state="disabled", fg_color="gray")
        self.log("🔄 已清除上傳的表結構，恢復為預設資料表！")

    def log(self, message):
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")

    def get_next_filename(self, base_name, extension):
        # 🌟 加入 Mac/Windows 打包專用的魔法路徑邏輯
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
        self.start_btn.configure(state="disabled", text="⏳ 地端算力燃燒中...")
        self.generated_data = []
        # 啟動執行緒，避免介面卡死
        threading.Thread(target=self.generate_data, daemon=True).start()

    def generate_data(self):
        # 🌟 透過字典，把 UI 選的中文，轉換回正確的 Ollama ID
        display_model_name = self.model_combo.get()
        model_name = self.model_mapping.get(display_model_name, "llama3.1")
        
        count = int(self.count_entry.get())
        selected_option = self.intent_combo.get().split(" ")[0] 
        
        if self.is_mysql_mode:
            self.log(f"🔥 呼叫 Ollama ({model_name}) 生成 {count} 筆 `{selected_option}` SQL...")
            
            # 🌟 自訂表 Prompt 邏輯 (移植雲端版)
            if selected_option.startswith("自訂表:"):
                selected_option = self.custom_table_name 
                prompt = f"請根據以下的資料表結構，生成 {count} 筆符合格式的 MySQL INSERT 語法。\n純SQL輸出，每行一條，嚴禁 markdown 標籤或解說。\n表結構如下：\n{self.custom_schema_content}"
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
            self.log(f"🔥 呼叫 Ollama ({model_name}) 生成 {count} 筆 `{intent}` NLP 訓練句子...")
            prompt_templates = {
                "RECORD": f"生成 {count} 句台灣人「記帳」的口語說法。必須包含金額和項目。例如：午餐100元。直接列表輸出，一行一句。",
                "QUERY": f"生成 {count} 句台灣人「查帳、問預算、問餘額」的口語說法。直接列表輸出，一行一句。",
                "CHAT": f"生成 {count} 句跟理財助手「閒聊、無意義」的說法。直接列表輸出，一行一句。",
                "ADVISOR": f"生成 {count} 句向理財顧問「尋求建議、評估消費」的說法。直接列表輸出，一行一句。",
                "KNOWLEDGE": f"生成 {count} 句詢問「系統操作、成就解鎖規則」的說法。直接列表輸出，一行一句。"
            }
            prompt = prompt_templates[intent]
        
        # Ollama API 設定
        url = "http://localhost:11434/api/generate"
        payload = {
            "model": model_name, 
            "prompt": prompt, 
            "stream": False, # 地端打包不建議用 stream，介面處理較複雜
            "options": {
                "temperature": 0.7,
                "num_predict": 4096 # 限制生成長度，避免無限生成
            }
        }
        
        try:
            # 🌟 地端模型算較久，Timeout 放寬到 600 秒
            response = requests.post(url, json=payload, timeout=600)
            
            if response.status_code == 200:
                result_text = response.json().get("response", "").strip()
                
                # 處理 Markdown 清理
                if "```sql" in result_text: 
                    result_text = result_text.split("```sql")[1].split("```")[0].strip()
                elif "```" in result_text: 
                    result_text = result_text.split("```")[1].strip()

                lines = result_text.split('\n')
                success_count = 0
                for line in lines:
                    clean_line = line.strip("1234567890.、- *\"'")
                    # 依據模式判斷合理長度，避免存入空行
                    if len(clean_line) > 10 if self.is_mysql_mode else len(clean_line) > 2:
                        if self.is_mysql_mode:
                            # 簡單檢查是否為 INSERT 語法
                            if "INSERT" in line.upper():
                                self.generated_data.append(line.strip())
                                success_count += 1
                        else:
                            self.generated_data.append({"text": clean_line, "intent": selected_option})
                            success_count += 1
                        
                        # Log 前 5 筆示意外
                        if success_count <= 5: self.log(f"✔️ {clean_line[:60]}...")
                
                if success_count > 0:
                    self.log(f"\n✅ 成功獲取 {success_count} 筆資料！")
                    self.save_to_file(selected_option)
                else:
                    self.log(f"\n⚠️ AI 有回覆，但格式解析失敗。回覆內容摘要：{result_text[:100]}...")
                    
            else:
                self.log(f"❌ 錯誤：Ollama 回傳狀態碼 {response.status_code}")
                
        except requests.exceptions.Timeout:
            self.log(f"❌ 連線超時！地端模型算太久了。\n建議：減少生成數量，或改用 Llama 3.2 3B 模型。")
        except requests.exceptions.RequestException as e:
            self.log(f"❌ 無法連線至 Ollama！請確保 Ollama 已開啟且已下載模型。\n錯誤詳情: {str(e)}")
            
        finally:
            self.start_btn.configure(state="normal", text="🚀 地端加速生成")

    def save_to_file(self, base_name):
        if not self.generated_data: return
        
        if self.is_mysql_mode:
            # 存成 SQL
            filename = self.get_next_filename(f"{base_name}_mock", "sql")
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    for sql_line in self.generated_data:
                        f.write(sql_line + "\n")
                self.log(f"💾 SQL 語法已成功儲存至: {filename}")
            except Exception as e:
                self.log(f"❌ SQL 儲存失敗: {str(e)}")
            
        else:
            # 存成 Excel
            filename = self.get_next_filename(base_name, "xlsx")
            df = pd.DataFrame(self.generated_data)
            try:
                df.to_excel(filename, index=False)
                self.log(f"💾 NLP 訓練集已成功儲存至: {filename}")
            except PermissionError:
                self.log(f"❌ 儲存失敗！請確保 Excel 檔案 [{filename}] 沒有在其他程式中開啟。")
            except Exception as e:
                self.log(f"❌ Excel 儲存失敗: {str(e)}")

if __name__ == "__main__":
    # 簡單檢查 Ollama 是否在運行
    try:
        requests.get("http://localhost:11434/", timeout=2)
    except:
        print("⚠️ 警告: 未偵測到 Ollama 運行中，程式仍會啟動，但生成功能將無法使用。")
        print("👉 請確保已安裝並開啟 Ollama ([https://ollama.com/](https://ollama.com/))")

    app = DataGeneratorApp()
    app.mainloop()
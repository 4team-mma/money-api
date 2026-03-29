# python data_generator_v2.py
import customtkinter as ctk
import requests
import pandas as pd
import threading
import os
import glob
import sys
import tkinter.filedialog as fd
import time

# 🎨 系統外觀設定
ctk.set_appearance_mode("Dark")  
ctk.set_default_color_theme("blue") # 藍色主題

# 🧠 MMA 系統專屬知識庫 (壓縮提煉版，用於餵給 AI 確保假資料準確性)
SYSTEM_KNOWLEDGE = """
【系統名稱】：Money MMA 數位財務管理系統
【核心功能】：記帳、預算控管、圖表分析、結合政府CPI物價指數比對通膨、薪資爬蟲分析競爭力。
【預算與類別】：
- 預設支出類別(不可刪)：飲食🍔、交通🚗、居家🏠、娛樂🎮。
- 預設標籤(不可刪)：需要(深藍)、想要(綠)、旅遊(淺藍)。
- 預設收入：工資💰、獎金🏦、投資🐷。成員：自己、父母、孩子。
- 預算進度條：<30%綠色(安全)，30~79%藍色(正常)，>=80%紅色(警告即將超支)。
【成就與任務系統】：
- 每日任務：3個(Common/Rare/Epic)。分為「純XP任務」(30種) 與「卡牌掉落任務」(20種)。
- 連續簽到：7天一循環。1-3天10XP，4-6天20XP，第7天50XP。滿10次或全勤有隱藏驚喜。
【MBTI 喵喵卡牌】：共20張，分4組(各4張普通+1張稀有)。
- SJ守護者組：財務防守(管理貓,檢查貓,供應貓,守護貓) -> 解鎖木質主題。稀有:金字塔貓。
- NF外交官組：心靈平衡(主角貓,提倡貓,競選貓,調停貓) -> 解鎖年度圖表。稀有:獨角獸貓。
- SP探險家組：市場機會(冒險貓,鑒賞貓,表演貓,藝術貓) -> 解鎖深海主題。稀有:狂暴山貓。
- NT分析家組：戰略佈局(指揮貓,策劃貓,發明貓,邏輯貓) -> 解鎖流金主題。稀有:宇宙貓。
"""

class DataGeneratorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("白白AI資料生成器 (地端 Ollama 豪華知識版)")
        self.geometry("850x1000") # 加高以容納 Prompt 編輯區
        
        # --- UI 介面佈局 ---
        self.title_label = ctk.CTkLabel(self, text="🤖 Ollama 地端資料生成器", font=("Arial", 24, "bold"))
        self.title_label.pack(pady=10)
        
        # 🧠 模型設定區
        self.model_frame = ctk.CTkFrame(self)
        self.model_frame.pack(pady=5, padx=20, fill="x")
        ctk.CTkLabel(self.model_frame, text="本地 Ollama 模型:").pack(side="left", padx=10, pady=10)
        
        self.model_mapping = {
            "Llama 3.1 8B (綜合性能最強/台灣口語好)": "llama3.1",
            "DeepSeek R1 8B (最強推理思維/複雜 SQL)": "deepseek-r1:8b",
            "Gemma 2 9B (Google出品/邏輯嚴謹/稍慢)": "gemma2",
            "Llama 3.2 3B (極速生成/輕量首選)": "llama3.2",
            "Gemma 3 4B (小巧聰明/適合日常邏輯)": "gemma3:4b",
            "Gemma 3 1B (極度輕量/幾乎不佔資源)": "gemma3:1b"
        }
        
        self.model_combo = ctk.CTkComboBox(self.model_frame, values=list(self.model_mapping.keys()), width=350)
        self.model_combo.set("Llama 3.1 8B (綜合性能最強/台灣口語好)") 
        self.model_combo.pack(side="left", padx=10)
        
        self.mode_switch = ctk.CTkSwitch(self.model_frame, text="開啟 MySQL 模式", command=self.toggle_mode)
        self.mode_switch.pack(side="right", padx=20)

        # 🌟 單項式 / 多項式 選項區塊
        self.intent_mode_frame = ctk.CTkFrame(self)
        self.intent_mode_frame.pack(pady=5, padx=20, fill="x")
        ctk.CTkLabel(self.intent_mode_frame, text="句型模式:").pack(side="left", padx=10, pady=10)
        
        self.intent_mode_var = ctk.StringVar(value="SINGLE")
        self.rb_single = ctk.CTkRadioButton(self.intent_mode_frame, text="單項目 (一句一筆/單一意圖)", variable=self.intent_mode_var, value="SINGLE", command=self.on_intent_change)
        self.rb_single.pack(side="left", padx=20)
        self.rb_multi = ctk.CTkRadioButton(self.intent_mode_frame, text="多項目 (2~3筆混合/多意圖)", variable=self.intent_mode_var, value="MULTI", command=self.on_intent_change)
        self.rb_multi.pack(side="left", padx=20)

        # 意圖/資料表選擇與數量
        self.setting_frame = ctk.CTkFrame(self)
        self.setting_frame.pack(pady=5, padx=20, fill="x")
        
        self.intent_label = ctk.CTkLabel(self.setting_frame, text="生成類別:")
        self.intent_label.grid(row=0, column=0, padx=10, pady=10)
        
        self.nlp_options = ["RECORD (記帳)", "QUERY (查詢)", "CHAT (閒聊)", "ADVISOR (顧問)", "KNOWLEDGE (手冊)"]
        self.mysql_options = ["adds (帳單紀錄)", "budgets (預算設定)", "savings_goals (儲蓄目標)", "accounts (我的帳戶)", "transactions (轉帳紀錄)", "feedbacks (意見回饋)"]
        
        self.intent_combo = ctk.CTkComboBox(self.setting_frame, values=self.nlp_options, width=180, command=self.on_intent_change)
        self.intent_combo.grid(row=0, column=1, padx=5, pady=10)
        
        self.upload_btn = ctk.CTkButton(self.setting_frame, text="📁 上傳自訂表", command=self.upload_schema, fg_color="gray", state="disabled", width=120)
        self.upload_btn.grid(row=0, column=2, padx=5, pady=10)
        
        self.reset_btn = ctk.CTkButton(self.setting_frame, text="🔄 恢復預設", command=self.reset_schema, fg_color="gray", state="disabled", width=100)
        self.reset_btn.grid(row=0, column=3, padx=5, pady=10)
        
        self.custom_schema_content = "" 
        self.custom_table_name = ""     
        
        ctk.CTkLabel(self.setting_frame, text="生成數量:").grid(row=1, column=0, padx=10, pady=10)
        self.count_entry = ctk.CTkEntry(self.setting_frame, width=80)
        self.count_entry.insert(0, "50") 
        self.count_entry.grid(row=1, column=1, padx=10, pady=10)

        # 🌟 全新升級：Prompt 預覽與編輯區
        self.prompt_frame = ctk.CTkFrame(self)
        self.prompt_frame.pack(pady=5, padx=20, fill="x")
        
        self.prompt_top_frame = ctk.CTkFrame(self.prompt_frame, fg_color="transparent")
        self.prompt_top_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(self.prompt_top_frame, text="✏️ Prompt 預覽與自訂 (可直接修改):", font=("Arial", 14, "bold")).pack(side="left")
        
        self.save_prompt_btn = ctk.CTkButton(self.prompt_top_frame, text="💾 更新並鎖定 Prompt", width=120, command=self.lock_custom_prompt)
        self.save_prompt_btn.pack(side="right", padx=5)
        
        self.reset_prompt_btn = ctk.CTkButton(self.prompt_top_frame, text="🔄 恢復預設", width=80, fg_color="gray", command=self.on_intent_change)
        self.reset_prompt_btn.pack(side="right", padx=5)

        self.prompt_box = ctk.CTkTextbox(self.prompt_frame, height=100, font=("Arial", 14))
        self.prompt_box.pack(pady=5, padx=10, fill="both", expand=True)
        self.is_prompt_locked = False # 用來記錄使用者是否有自訂 Prompt

        # Log 顯示區
        self.log_box = ctk.CTkTextbox(self, height=200, font=("Arial", 14))
        self.log_box.pack(pady=5, padx=20, fill="both", expand=True)
        
        # 📊 進度條與時間標籤
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.pack(pady=5, padx=20, fill="x")
        
        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, width=400)
        self.progress_bar.pack(pady=5)
        self.progress_bar.set(0)        
        
        self.progress_label = ctk.CTkLabel(self.progress_frame, text="進度: 0% | 耗時: 0.0s", font=("Arial", 12))
        self.progress_label.pack()

        # 按鈕區
        self.start_btn = ctk.CTkButton(self, text="🚀 地端加速生成", command=self.start_generation_thread, height=40, font=("Arial", 16, "bold"))
        self.start_btn.pack(pady=10)
        
        self.generated_data = []
        self.is_mysql_mode = False
        self.start_time = 0

        # 初始化時，載入預設的 Prompt
        self.on_intent_change()

    def get_default_prompt_template(self):
        """🌟 根據目前選項，回傳預設的 Prompt 內容"""
        selected_option = self.intent_combo.get().split(" ")[0]
        mode_choice = self.intent_mode_var.get()
        
        if self.mode_switch.get() == 1: # MySQL 模式
            if selected_option.startswith("自訂表:"):
                return f"請根據以下的資料表結構，生成 1 筆 MySQL INSERT 語法。嚴禁 markdown 標籤。\n表結構：\n{self.custom_schema_content}"
            elif selected_option == "adds":
                return "生成 1 筆 MySQL INSERT 至 `adds` 表。規則: add_type=1(收入,類別:工資/獎金/投資, icon:💰/🏦/🐷), add_type=0(支出,類別:飲食/交通/居家/娛樂, icon:🍔/🚗/🏠/🎮), add_amount(50~5000), add_note(10字內)。"
            elif selected_option == "accounts":
                return "生成 1 筆 INSERT 至 `accounts` 表。欄位包含: account_type, account_name, initial_balance(1000~50000), current_balance, account_icon(💳/🏦)。"
            elif selected_option == "feedbacks":
                return "生成 1 筆 INSERT 至 `feedbacks` 表。欄位: question_type(系統Bug/功能建議), use_page, content(模擬抱怨或建議20字內)。"
            else: 
                return f"生成 1 筆 INSERT INTO 語法新增至 `{selected_option}` 表。user_id=1。"
        else: # NLP 模式
            if mode_choice == "MULTI":
                prompts = {
                    "RECORD": "生成 1 句台灣人「一次記多筆帳」的自然口語。嚴格規則：1.只能包含 2 到 3 個日常消費項目，絕對不能超過 3 個！2.大約80%順著講(如:買包子20元然後喝飲料55元)，只有20%機率在句尾加總計(如:午餐100下午咖啡60總共160元)。3.限制在記帳領域。",
                    "QUERY": "生成 1 句台灣人「一次查詢多個財務資訊」的口語。例如：『幫我查一下這個月的飲食預算剩多少，順便看一下銀行帳戶總餘額』。限制在個人財務管理。",
                    "CHAT": "生成 1 句跟理財助手「閒聊多個財務狀況」的說法。例如：『最近好像花太多錢了，覺得有點焦慮，而且這個月都沒存到錢』。",
                    "ADVISOR": "結合系統知識，生成 1 句向顧問「一次詢問多個理財或預算建議」的說法。例如：『我該怎麼分配交通跟娛樂預算？還有獎金建議拿去投資嗎？』",
                    "KNOWLEDGE": "結合系統知識，生成 1 句詢問「系統操作」並包含多個問題的說法。例如：『SJ守護者組的卡牌怎麼收集？還有連續簽到第七天會給多少XP？』"
                }
                return prompts.get(selected_option, "")
            else:
                prompts = {
                    "RECORD": "生成 1 句台灣人「單純記一筆帳」的口語說法。必須包含金額和項目，例如：午餐100元。",
                    "QUERY": "生成 1 句台灣人「查帳、問預算、問餘額」的口語說法。",
                    "CHAT": "生成 1 句跟理財助手「關於財務與省錢的閒聊」的說法。",
                    "ADVISOR": "結合系統知識，生成 1 句向理財顧問「尋求單一理財建議」的說法。",
                    "KNOWLEDGE": "結合系統知識，生成 1 句詢問「單一系統操作(如:怎麼解鎖卡牌/CPI功能是什麼)」的說法。"
                }
                return prompts.get(selected_option, "")

    def on_intent_change(self, *args):
        """🌟 當使用者切換選項時，自動更新 Prompt 文字框"""
        self.is_prompt_locked = False # 切換選項自動解除鎖定
        default_prompt = self.get_default_prompt_template()
        self.prompt_box.delete("1.0", "end")
        self.prompt_box.insert("end", default_prompt)

    def lock_custom_prompt(self):
        """🌟 使用者按下更新並鎖定按鈕"""
        self.is_prompt_locked = True
        self.log("✅ Prompt 已手動更新並鎖定！接下來將使用您自訂的內容生成。")

    def toggle_mode(self):
        self.log_box.delete("1.0", "end") 
        self.is_mysql_mode = self.mode_switch.get() == 1
        
        if self.is_mysql_mode:
            self.intent_combo.configure(values=self.mysql_options)
            self.intent_combo.set(self.mysql_options[0])
            self.upload_btn.configure(state="normal", fg_color="#1f538d")
            self.rb_single.configure(state="disabled")
            self.rb_multi.configure(state="disabled")
            self.log("🔄 已切換為【MySQL 假資料模式】！(支援上傳自訂表結構)")
        else:
            self.intent_combo.configure(values=self.nlp_options)
            self.intent_combo.set(self.nlp_options[0])
            self.upload_btn.configure(state="disabled", fg_color="gray")
            self.reset_btn.configure(state="disabled", fg_color="gray")
            self.rb_single.configure(state="normal")
            self.rb_multi.configure(state="normal")
            self.custom_schema_content = "" 
            self.log("🔄 已切換為【Keras 意圖訓練模式】！")
        
        # 切換模式後，更新 Prompt 文字框
        self.on_intent_change()

    def upload_schema(self):
        path = fd.askopenfilename(filetypes=[("SQL/TXT", "*.sql *.txt")])
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
                self.log(f"📁 成功載入自訂表結構 [{self.custom_table_name}]！")
                
                # 載入後自動更新 Prompt
                self.on_intent_change()
            except Exception as e:
                self.log(f"❌ 讀取檔案失敗: {str(e)}")

    def reset_schema(self):
        self.custom_schema_content = ""
        self.custom_table_name = ""
        self.intent_combo.configure(values=self.mysql_options)
        self.intent_combo.set(self.mysql_options[0])
        self.reset_btn.configure(state="disabled", fg_color="gray")
        self.log("🔄 已清除上傳的表結構，恢復為預設資料表！")
        self.on_intent_change()

    def log(self, message):
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")

    def get_next_filename(self, base_name, extension):
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
        self.start_btn.configure(state="disabled", text="⏳ 燃燒算力中...")
        self.generated_data = []
        
        # 啟動進度條與計時基準
        self.start_time = time.time()
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(0)
        self.progress_label.configure(text="進度: 0% | 耗時: 0.0s")
        
        threading.Thread(target=self.generate_data, daemon=True).start()

    def generate_data(self):
        display_model_name = self.model_combo.get()
        model_name = self.model_mapping.get(display_model_name, "llama3.1")
        total_count = int(self.count_entry.get())
        selected_option = self.intent_combo.get().split(" ")[0] 
        mode_choice = self.intent_mode_var.get()
        
        self.success_count = 0
        self.log(f"🔥 呼叫 Ollama ({model_name}) 開始生成 {total_count} 筆資料...")

        for i in range(total_count):
            try:
                # 🌟 直接讀取介面上使用者自訂 (或預設) 的 Prompt 內容！
                user_defined_prompt = self.prompt_box.get("1.0", "end").strip()
                
                if self.is_mysql_mode:
                    current_table_name = selected_option if not selected_option.startswith("自訂表:") else self.custom_table_name
                    final_prompt = f"{user_defined_prompt}\n純SQL輸出，嚴禁解釋。"
                else:
                    system_context = f"{SYSTEM_KNOWLEDGE}\n\n【重要強制規定】：請確保輸出文字絕對不能有簡體中文，有簡體字的一律換成台灣繁體中文！\n\n"
                    final_prompt = f"{system_context}任務：{user_defined_prompt}\n請直接輸出 1 句口語句子，嚴禁任何解釋或引號："

                # 🚀 呼叫地端 Ollama API
                url = "http://localhost:11434/api/generate"
                payload = {
                    "model": model_name, 
                    "prompt": final_prompt, 
                    "stream": False,
                    "options": {"temperature": 0.85, "num_predict": 128} 
                }
                
                response = requests.post(url, json=payload, timeout=60) # 60秒超時保護
                if response.status_code == 200:
                    res_text = response.json().get("response", "").strip().strip("1234567890.、- *\"'")
                    
                    if len(res_text) > 2:
                        if self.is_mysql_mode:
                            self.generated_data.append(res_text)
                        else:
                            label = f"MULTI_{selected_option}" if mode_choice == "MULTI" else selected_option
                            self.generated_data.append({"text": res_text, "intent": label})
                        
                        self.success_count += 1
                        
                        if self.success_count % 3 == 0 or self.success_count <= 3: 
                            self.log(f"✔️ [{self.success_count}] {res_text[:50]}...")
                else:
                    self.log(f"⚠️ 第 {i+1} 筆生成異常，狀態碼: {response.status_code}")

            except requests.exceptions.ConnectionError:
                self.log("❌ 錯誤：無法連線至 Ollama！請確認 Ollama 軟體是否已啟動。")
                break 
            except Exception as e:
                self.log(f"⚠️ 第 {i+1} 筆發生超時或錯誤: {str(e)}，跳過並繼續下一筆...")
                continue 
            
            # 🔄 更新進度條與時間
            elapsed = time.time() - self.start_time
            progress_pct = (i + 1) / total_count
            self.progress_bar.set(progress_pct)
            self.progress_label.configure(text=f"進度: {int(progress_pct * 100)}% ({i+1}/{total_count}) | 耗時: {elapsed:.1f}s")

        # ==========================
        # 🏁 迴圈結束，收尾存檔
        # ==========================
        self.progress_bar.set(1.0)
        duration = time.time() - self.start_time
        self.progress_label.configure(text=f"✅ 完成！總耗時: {duration:.1f} 秒")
        self.start_btn.configure(state="normal", text="🚀 地端加速生成")
        
        if self.success_count > 0:
            self.log(f"\n✨ 生成完畢！預計 {total_count} 筆，成功產出 {self.success_count} 筆。")
            save_name = current_table_name if self.is_mysql_mode else selected_option
            self.save_to_file(save_name)

    def save_to_file(self, base_name):
        if not self.generated_data: return
        
        if self.is_mysql_mode:
            filename = self.get_next_filename(f"{base_name}_mock", "sql")
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    for sql_line in self.generated_data:
                        f.write(sql_line + "\n")
                self.log(f"💾 SQL 已成功儲存至: {filename}")
            except Exception as e:
                self.log(f"❌ SQL 儲存失敗: {str(e)}")
                
        else:
            filename = self.get_next_filename(base_name, "xlsx")
            df = pd.DataFrame(self.generated_data)
            try:
                df.to_excel(filename, index=False)
                self.log(f"💾 NLP 訓練集已成功儲存至: {filename}")
            except PermissionError:
                self.log(f"❌ 儲存失敗！請確保 {filename} 沒有在 Excel 中開啟。")
            except Exception as e:
                self.log(f"❌ Excel 儲存失敗: {str(e)}")

if __name__ == "__main__":
    try:
        requests.get("http://localhost:11434/", timeout=2)
    except:
        print("⚠️ 警告: 未偵測到 Ollama 運行中，程式仍會啟動，但生成功能將無法使用。")
        print("👉 請確保已安裝並開啟 Ollama (https://ollama.com/)")

    app = DataGeneratorApp()
    app.mainloop()
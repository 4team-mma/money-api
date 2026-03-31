# python groq_data_generator.py
import customtkinter as ctk
import csv
import threading
import os
import glob
import sys
import tkinter.filedialog as fd
from dotenv import load_dotenv
from groq import Groq
import groq
import time

# 嘗試讀取專案底下的 .env 檔案
load_dotenv()

# 🎨 系統外觀設定
ctk.set_appearance_mode("Dark")  
ctk.set_default_color_theme("green") # 綠色主題，與 Ollama 區分

# 🧠 MMA 系統專屬知識庫
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

class GroqDataGeneratorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("白白AI資料生成器 (雲端極速知識版)")
        self.geometry("750x950") # 加高以容納 Prompt 編輯區
        
        # --- UI 介面佈局 ---
        self.title_label = ctk.CTkLabel(self, text="😺MMA雲端資料生成器", font=("Arial", 24, "bold"))
        self.title_label.pack(pady=10)
        
        self.key_frame = ctk.CTkFrame(self)
        self.key_frame.pack(pady=5, padx=20, fill="x")
        ctk.CTkLabel(self.key_frame, text="Groq API Key:").pack(side="left", padx=10, pady=10)
        self.api_key_entry = ctk.CTkEntry(self.key_frame, width=400, show="*", placeholder_text="請貼上你的 GROQ_API_KEY")
        env_key = os.getenv("GROQ_API_KEY", "")
        if env_key: self.api_key_entry.insert(0, env_key)
        self.api_key_entry.pack(side="left", padx=10)

        self.model_frame = ctk.CTkFrame(self)
        self.model_frame.pack(pady=5, padx=20, fill="x")
        ctk.CTkLabel(self.model_frame, text="雲端 Groq 模型:").pack(side="left", padx=10, pady=10)
        
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
        
        self.mode_switch = ctk.CTkSwitch(self.model_frame, text="開啟 MySQL 假資料模式", command=self.toggle_mode)
        self.mode_switch.pack(side="right", padx=20)

        self.intent_mode_frame = ctk.CTkFrame(self)
        self.intent_mode_frame.pack(pady=5, padx=20, fill="x")
        ctk.CTkLabel(self.intent_mode_frame, text="句型模式:").pack(side="left", padx=10, pady=10)
        
        self.intent_mode_var = ctk.StringVar(value="SINGLE")
        self.rb_single = ctk.CTkRadioButton(self.intent_mode_frame, text="單項目 (一句一筆/單一意圖)", variable=self.intent_mode_var, value="SINGLE", command=self.on_intent_change)
        self.rb_single.pack(side="left", padx=20)
        self.rb_multi = ctk.CTkRadioButton(self.intent_mode_frame, text="多項目 (2~3筆混合/多意圖)", variable=self.intent_mode_var, value="MULTI", command=self.on_intent_change)
        self.rb_multi.pack(side="left", padx=20)

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
        self.count_entry.insert(0, "100") 
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

        self.prompt_box = ctk.CTkTextbox(self.prompt_frame, height=120, font=("Arial", 14))
        self.prompt_box.pack(pady=5, padx=10, fill="both", expand=True)
        self.is_prompt_locked = False

        self.log_box = ctk.CTkTextbox(self, height=200, font=("Arial", 14))
        self.log_box.pack(pady=5, padx=20, fill="both", expand=True)
        
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(pady=5)
        self.start_btn = ctk.CTkButton(self.btn_frame, text="🚀 雲端極速生成", command=self.start_generation_thread, height=40, font=("Arial", 16, "bold"))
        self.start_btn.pack(side="left", padx=10)
        
        self.generated_data = []
        self.is_mysql_mode = False
        
        self.progress_bar = ctk.CTkProgressBar(self, width=400)
        self.progress_bar.pack(pady=5)
        self.progress_bar.set(0)        
        self.progress_label = ctk.CTkLabel(self, text="準備就緒 | 耗時: 0.0s", font=("Arial", 12))
        self.progress_label.pack()
        
        self.is_generating = False
        self.start_time = 0

        # 初始載入預設 Prompt
        self.on_intent_change()

    def get_default_prompt_template(self):
        """🌟 根據目前選項，回傳預設的 Groq 批次 Prompt 內容"""
        selected_option = self.intent_combo.get().split(" ")[0]
        mode_choice = self.intent_mode_var.get()
        count = self.count_entry.get()
        if not count.isdigit(): count = "100"
        
        if self.mode_switch.get() == 1: # MySQL 模式
            if selected_option.startswith("自訂表:"):
                return f"請根據以下的資料表結構，生成 {count} 筆 MySQL INSERT 語法。表結構：\n{self.custom_schema_content}"
            elif selected_option == "adds":
                return f"生成 {count} 筆 MySQL INSERT 至 `adds` 表。規則: add_type=1(收入,類別:工資/獎金/投資, icon:💰/🏦/🐷), add_type=0(支出,類別:飲食/交通/居家/娛樂, icon:🍔/🚗/🏠/🎮), add_amount(50~5000), add_note(10字內)。"
            elif selected_option == "accounts":
                return f"生成 {count} 筆 INSERT 至 `accounts` 表。欄位包含: account_type, account_name, initial_balance(1000~50000), current_balance, account_icon(💳/🏦)。"
            elif selected_option == "feedbacks":
                return f"生成 {count} 筆 INSERT 至 `feedbacks` 表。欄位: question_type(系統Bug/功能建議), use_page, content(模擬抱怨或建議20字內)。"
            else: 
                return f"生成 {count} 筆 INSERT INTO 語法，新增至 `{selected_option}` 表。user_id 皆填 1。"
        else: # NLP 模式
            c = int(count)
            if mode_choice == "MULTI":
                prompts = {
                    "RECORD": f"【任務】：生成 {c} 句台灣人「一次記錄多筆消費」的自然口語。\n"
                              f"【重要特徵】：每一句必須包含 2 到 3 個明確金額與動詞，且必須使用連接詞（如：又、順便、加上、然後）。\n"
                              f"【比例控制】：{int(c*0.8)} 句不要加總計；{int(c*0.2)} 句結尾加上總額（如：總共180元）。\n"
                              f"【範例】：『早餐吃50元然後又買了杯35元的奶茶』、『剛交了房租1萬5順便付了水費300』。",
                    
                    "QUERY": f"【任務】：生成 {c} 句台灣人「一次查詢多個財務資訊」的口語。\n"
                             f"【重要特徵】：必須包含連接詞（如：順便、還有、再幫我、以及、也要看），內容包含餘額、預算、支出、收入。\n"
                             f"【範例】：『查一下我這週花了多少，還有下個月預算剩多少？』、『看我的錢包餘額，順便查飲食支出。』",
                    
                    "CHAT": f"【任務】：生成 {c} 句跟理財助手「閒聊多個財務心情」的說法。\n"
                            f"【重要特徵】：必須包含情緒詞（如：焦慮、爽、開心）與理財情境（如：省錢、存錢、花太多）。\n"
                            f"【數字控制】：只有 30% 的句子包含模糊數字（如：這個月又花幾千塊）。\n"
                            f"【範例】：『這個月好像花太多了，有點焦慮，而且都沒存到錢。』",
                    
                    "ADVISOR": f"【身分】：你是台灣使用者。任務：生成 {c} 句向顧問「尋求多個理財建議」的說法。\n"
                               f"【重要特徵】：每一句必須包含具體金額（如：10萬塊、月薪4萬），詢問投資、分配或預算建議。\n"
                               f"【範例】：『我月薪4萬該怎麼分配交通費？還有剩下的5000元建議存股嗎？』",
                    
                    "KNOWLEDGE": f"【任務】：生成 {c} 句詢問「系統規則或名詞解釋」且包含多個問題的說法。\n"
                                 f"【重要特徵】：包含連接詞，針對簽到、卡牌、XP、任務、CPI、薪資分析進行詢問。\n"
                                 f"【範例】：『SJ組的卡牌怎麼收集？還有簽到滿七天會送什麼？』"
                }
                return prompts.get(selected_option, "")
            else:
                prompts = {
                    "RECORD": f"生成 {c} 句台灣人「單純記一筆帳」的口語。必須包含 1 個金額與 1 個項目。範例：『午餐120元』、『剛剛買飲料花45塊』。",
                    "QUERY": f"生成 {c} 句台灣人「查詢單一財務資訊」的口語。範例：『我預算剩多少？』、『查一下這個月的支出』。",
                    "CHAT": f"生成 {c} 句關於理財心情的單純閒聊（不含記帳動作）。範例：『省錢真的好難喔』、『發票又沒中了，嗚嗚』。",
                    "ADVISOR": f"【身分】：台灣使用者。生成 {c} 句「尋求單一理財建議」的口語。必須含具體金額。範例：『我有10萬塊建議存哪裡？』。",
                    "KNOWLEDGE": f"生成 {c} 句詢問「單一系統操作或名詞」的說法。範例：『CPI是什麼？』、『卡牌在哪裡看？』。"
                }
                return prompts.get(selected_option, "")

    def on_intent_change(self, *args):
        """🌟 當使用者切換選項或修改數量時，自動更新 Prompt 文字框"""
        self.is_prompt_locked = False 
        default_prompt = self.get_default_prompt_template()
        self.prompt_box.delete("1.0", "end")
        self.prompt_box.insert("end", default_prompt)
        
        # 綁定數量改變時也自動更新 prompt (如果還沒被鎖定)
        self.count_entry.bind("<KeyRelease>", self.update_prompt_if_not_locked)

    def update_prompt_if_not_locked(self, event):
        if not self.is_prompt_locked:
            default_prompt = self.get_default_prompt_template()
            self.prompt_box.delete("1.0", "end")
            self.prompt_box.insert("end", default_prompt)

    def lock_custom_prompt(self):
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
            self.log("🔄 已切換為【MySQL 假資料模式】！")
        else:
            self.intent_combo.configure(values=self.nlp_options)
            self.intent_combo.set(self.nlp_options[0])
            self.upload_btn.configure(state="disabled", fg_color="gray")
            self.reset_btn.configure(state="disabled", fg_color="gray")
            self.rb_single.configure(state="normal")
            self.rb_multi.configure(state="normal")
            self.custom_schema_content = "" 
            self.log("🔄 已切換為【Keras 意圖訓練模式】！")
        self.on_intent_change()

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
                self.log(f"📁 成功載入自訂表結構 [{self.custom_table_name}]！")
                self.on_intent_change()
            except Exception as e:
                self.log(f"❌ 讀取檔案失敗: {str(e)}")

    def reset_schema(self):
        self.custom_schema_content = ""
        self.custom_table_name = ""
        self.intent_combo.configure(values=self.mysql_options)
        self.intent_combo.set(self.mysql_options[0])
        self.reset_btn.configure(state="disabled", fg_color="gray")
        self.log("🔄 已清除表結構，恢復為預設！")
        self.on_intent_change()

    def log(self, message):
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")

    def get_next_filename(self, base_name, extension):
        # mac 打包路徑
        if getattr(sys, 'frozen', False):
            if sys.platform == 'darwin' and '.app' in sys.executable:
                base_dir = os.path.abspath(os.path.join(os.path.dirname(sys.executable), '../../..'))
            else:
                base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        # 絕對路徑，確保資料夾會建立在app旁邊
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

    def update_timer(self):
        if self.is_generating:
            elapsed = time.time() - self.start_time
            self.progress_label.configure(text=f"⏳ 雲端極速運算中... 目前等待: {elapsed:.1f}s")
            self.after(100, self.update_timer)

    def start_generation_thread(self):
        api_key = self.api_key_entry.get().strip()
        if not api_key:
            self.log("❌ 錯誤：請先輸入 Groq API Key！")
            return
            
        self.start_btn.configure(state="disabled", text="⏳ 雲端運算中...")
        self.generated_data = []
        
        self.is_generating = True
        self.start_time = time.time()
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()
        self.update_timer()
        
        threading.Thread(target=self.generate_data, args=(api_key,), daemon=True).start()

    def generate_data(self, api_key):
        display_model_name = self.model_combo.get()
        model_name = self.model_mapping.get(display_model_name) or "llama-3.3-70b-versatile"
        count = self.count_entry.get()
        selected_option = self.intent_combo.get().split(" ")[0] 
        mode_choice = self.intent_mode_var.get()
        
        # 🌟 核心：直接讀取使用者在介面上修改好的 Prompt
        user_defined_prompt = self.prompt_box.get("1.0", "end").strip()
        
        if self.is_mysql_mode:
            self.log(f"🔥 連線 Groq ({model_name}) 批次生成 {count} 筆 SQL...")
            final_prompt = f"{user_defined_prompt}\n純SQL輸出，每行一條，嚴禁markdown與解釋。"
        else:
            mode_text = "多項式" if mode_choice == "MULTI" else "單項式"
            self.log(f"🔥 連線 Groq ({model_name}) 批次生成 {count} 筆 `{selected_option}` {mode_text}句子...")
            system_context = f"{SYSTEM_KNOWLEDGE}\n\n【重要強制規定】：請確保輸出文字絕對不能有簡體中文，有簡體字的一律換成台灣繁體中文！\n\n"
            final_prompt = f"{system_context}任務：{user_defined_prompt}\n請直接列表輸出這 {count} 句，一行一句，嚴禁任何解釋或引號："
        
        try:
            client = Groq(api_key=api_key)
            response = client.chat.completions.create(
                messages=[{"role": "user", "content": final_prompt}],
                model=model_name,
                temperature=0.8, 
            )
            
            content = response.choices[0].message.content
            result_text = str(content).strip() if content is not None else ""
                
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
                        final_intent = f"MULTI_{selected_option}" if mode_choice == "MULTI" else selected_option
                        self.generated_data.append({"text": clean_line, "intent": final_intent})
                    
                    if success_count < 10: 
                        self.log(f"✔️ {clean_line[:60]}...")
                    success_count += 1
            
            self.log(f"\n✅ 成功獲取 {success_count} 筆資料！(Groq 官方通道連線成功！)")
            
            # 儲存檔案
            save_name = selected_option if not (self.is_mysql_mode and selected_option.startswith("自訂表:")) else self.custom_table_name
            self.save_to_file(save_name)

        except groq.AuthenticationError:
            self.log("❌ 錯誤：Groq 官方驗證失敗 (401)！請確認金鑰是否過期或被官方停用。")
        except Exception as e:
            self.log(f"❌ 連線失敗！\n錯誤原因：{e}\n建議：請檢查網路或稍後再試。")
            
        finally:
            self.is_generating = False
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
            self.progress_bar.set(1.0) 
            
            total_time = time.time() - self.start_time
            self.progress_label.configure(text=f"✅ 完成！總耗時: {total_time:.1f} 秒")
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
            # 如果想降低大小不用panda可以改存csv
            filename = self.get_next_filename(base_name, "csv")
            # df = pd.DataFrame(self.generated_data)
            try:
                with open(filename, 'w', newline='',            encoding='utf-8-sig') as f:
                    writer = csv.DictWriter(f, fieldnames=["text", "intent"])
                    writer.writeheader()
                    writer.writerows(self.generated_data)
                self.log(f"💾 NLP 訓練集已成功儲存.csv至: {filename}")
                
            except PermissionError:
                self.log(f"❌ 儲存失敗！請確保 {filename} 沒有在 Excel 中開啟。")

if __name__ == "__main__":
    app = GroqDataGeneratorApp()  
    app.mainloop()
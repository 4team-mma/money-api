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
# import json
import random
import time

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

        self.nlp_options = ["RECORD (記帳)", "QUERY (查詢)", "CHAT (閒聊)", "ADVISOR (顧問)", "KNOWLEDGE (手冊)", "MULTI-INTENT (混合意圖)"]

        self.mysql_options = ["adds (帳單紀錄)", "budgets (預算設定)", "savings_goals (儲蓄目標)", "accounts (我的帳戶)", "transactions (轉帳紀錄)", "feedbacks (意見回饋)"]

        # 新增一個混合設定區 (預設隱藏)
        self.mixed_config_frame = ctk.CTkFrame(self.setting_frame, fg_color="transparent")
        # 注意：這裡先不 pack，等切換到 MULTI-INTENT 才顯示

        self.mixed_config_frame = ctk.CTkFrame(self.setting_frame, fg_color="transparent")

        ctk.CTkLabel(self.mixed_config_frame, text="混合比例 (多意圖 %):").pack(side="left", padx=5)
        self.mixed_ratio_slider = ctk.CTkSlider(self.mixed_config_frame, from_=10, to=100, number_of_steps=9, width=150)
        self.mixed_ratio_slider.set(30)
        self.mixed_ratio_slider.pack(side="left", padx=5)

        self.ratio_val_label = ctk.CTkLabel(self.mixed_config_frame, text="30%")
        self.ratio_val_label.pack(side="left", padx=2)
        self.mixed_ratio_slider.configure(command=lambda v: self.ratio_val_label.configure(text=f"{int(v)}%"))


        self.intent_combo = ctk.CTkComboBox(self.setting_frame, values=self.nlp_options, width=220, command=self.check_intent_mode)
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

        # 新增進度條
        self.progress_bar = ctk.CTkProgressBar(self, width=400)
        self.progress_bar.pack(pady=5)
        self.progress_bar.set(0) # 預設值為 0
        self.progress_label = ctk.CTkLabel(self, text="進度: 0%", font=("Arial", 12))
        self.progress_label.pack()

    # 🌟 新增：檢查是否選到混合意圖，動態顯示 UI
    def check_intent_mode(self, choice):
        if choice == "MULTI-INTENT (混合意圖)":
            # 顯示比例設定，放在 grid 的右側
            self.mixed_config_frame.grid(row=1, column=2, columnspan=2, padx=10, pady=10)
            self.log("💡 已開啟混合意圖模式：可調整單句中『混合多個意圖』的出現比例。")
        else:
            # 隱藏比例設定
            self.mixed_config_frame.grid_forget()

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
            # 1. 取得基本 UI 參數
            start_time = time.time() # ⏳ 開始計時
            display_model_name = self.model_combo.get()
            model_name = self.model_mapping.get(display_model_name, "llama3.1")
            count = int(self.count_entry.get())
            selected_option = self.intent_combo.get()

            # 基礎 NLP 意圖 Prompt 指南
            intent_prompts = {
                "RECORD": "台灣人『記帳』口語，包含金額項目，如：午餐100元",
                "QUERY": "台灣人『查帳、問預算、問餘額』，如：我還剩多少錢",
                "CHAT": "與理財助手的『生活閒聊』，如：今天天氣不錯",
                "ADVISOR": "向理財顧問『尋求建議或評估』，如：這筆錢建議花嗎",
                "KNOWLEDGE": "詢問『系統規則或操作』，如：怎麼解鎖成就"
            }

            self.success_count = 0
            self.generated_data = [] # 確保開始前清空舊資料
            self.progress_bar.set(0) # 重置進度條

            # --- A. MySQL 模式：一次生成整批 (因 Prompt 已寫好生成 count 筆) ---
            if self.is_mysql_mode:
                self.log(f"🔥 呼叫 Ollama ({model_name}) 生成 {count} 筆 `{selected_option}` SQL...")
                # 這裡因為是批量生成，進度條直接跳到 50% 代表處理中
                self.progress_bar.set(0.5)
                self.progress_label.configure(text="SQL 生成中...")

                # 完全保留你原本的 MySQL Prompt 邏輯
                if selected_option.startswith("自訂表:"):
                    current_table_name = self.custom_table_name
                    prompt = f"請根據以下的資料表結構，生成 {count} 筆符合格式的 MySQL INSERT 語法。\n純SQL輸出，每行一條，嚴禁 markdown 標籤或解說。\n表結構如下：\n{self.custom_schema_content}"
                elif selected_option == "adds":
                    current_table_name = "adds"
                    prompt = f"生成 {count} 筆 MySQL INSERT 語法新增至 `adds` 表。\n規則: user_id(1), account_id(1), add_date(2025-10-01到2026-03-31), add_type=1(收入,類別:工資/獎金/投資, icon:💰/🏦/🐷), add_type=0(支出,類別:飲食/交通/居家/娛樂, icon:🍔/🚗/🏠/🎮), add_member(自己/父母/孩子), add_tag(需要/想要/旅遊), add_amount(50~5000), add_note(具體項目10字內)。\n純SQL輸出每行一條，嚴禁markdown。"
                elif selected_option == "accounts":
                    current_table_name = "accounts"
                    prompt = f"生成 {count} 筆 INSERT 語法至 `accounts` 表。\n欄位: user_id(1), account_type('cash'或'bank'), account_name(如:國泰世華), currency('NT$'), initial_balance(1000~50000), current_balance(同 initial_balance), exclude_from_assets(0或1), account_icon(💳 或 🏦)。\n純SQL輸出每行一條。"
                elif selected_option == "feedbacks":
                    current_table_name = "feedbacks"
                    prompt = f"生成 {count} 筆 INSERT 語法至 `feedbacks` 表。\n欄位: user_id(1), feedback_name(如:王小明), question_type(系統Bug/功能建議), use_page(首頁/記帳頁), content(模擬抱怨或建議20字內)。\n純SQL輸出每行一條。"
                else:
                    current_table_name = selected_option
                    prompt = f"生成 {count} 筆 INSERT INTO 語法，新增至 `{selected_option}` 表。user_id 皆填 1。純SQL輸出每行一條。"

                # 執行 API 呼叫 (SQL 模式)
                try:
                    url = "http://localhost:11434/api/generate"
                    payload = {"model": model_name, "prompt": prompt, "stream": False, "options": {"temperature": 0.5}}
                    response = requests.post(url, json=payload, timeout=90)
                    if response.status_code == 200:
                        raw_sql = response.json().get("response", "").strip()
                        sql_lines = [line.strip() for line in raw_sql.split('\n') if "INSERT" in line.upper()]
                        self.generated_data = sql_lines
                        self.success_count = len(sql_lines)
                        for i, line in enumerate(sql_lines[:3]): self.log(f"✔️ SQL {i+1}: {line[:50]}...")

                    if self.success_count > 0:
                        self.log(f"\n✅ 成功獲取 {self.success_count} 筆 SQL 資料！")
                        self.save_to_file(current_table_name)
                        self.progress_bar.set(1.0)
                except Exception as e:
                    self.log(f"❌ SQL 生成失敗: {str(e)}")

            # --- B. NLP 訓練模式：逐筆生成 (為了處理隨機混合意圖) ---
            else:
                self.log(f"🔥 呼叫 Ollama ({model_name}) 生成 {count} 筆訓練資料...")
                self.log(f"🔥 啟動逐筆生成模式 (共 {count} 筆)...")
                for i in range(count):
                    current_labels = []
                    # 1. 更新進度條 UI
                    progress_pct = (i + 1) / count
                    self.progress_bar.set(progress_pct)
                    self.progress_label.configure(text=f"進度: {int(progress_pct * 100)}% ({i+1}/{count})")

                    if selected_option == "MULTI-INTENT (混合意圖)":
                        ratio = self.mixed_ratio_slider.get() / 100.0
                        if random.random() < ratio:
                            # 隨機抽 2~3 個意圖
                            num_mix = random.choices([2, 3], weights=[0.8, 0.2])[0]
                            mix_keys = random.sample(list(intent_prompts.keys()), num_mix)

                            prompt = f"請將以下 {num_mix} 個意圖組合成一句自然的台灣口語（中間用『，順便』或『，而且』等連接詞）：\n"
                            for j, k in enumerate(mix_keys):
                                prompt += f"{j+1}. {intent_prompts[k]}\n"
                            prompt += "直接輸出句子，嚴禁解釋。"
                            current_labels = mix_keys
                        else:
                            # 單意圖 (隨機抽出一個)
                            target = random.choice(list(intent_prompts.keys()))
                            prompt = f"請生成一句{intent_prompts[target]}。直接輸出句子。"
                            current_labels = [target]
                    else:
                        # 原本的單意圖固定模式
                        intent_key = selected_option.split(" ")[0]
                        prompt = f"請生成一句{intent_prompts.get(intent_key, '生活對話')}。直接輸出句子。"
                        current_labels = [intent_key]

                    # 呼叫 API (NLP 模式逐筆呼叫)
                    try:
                        url = "http://localhost:11434/api/generate"
                        payload = {
                            "model": model_name,
                            "prompt": prompt,
                            "stream": False,
                            "options": {"temperature": 0.8, "num_predict": 128}
                        }
                        response = requests.post(url, json=payload, timeout=30)
                        if response.status_code == 200:
                            res_json = response.json()
                            clean_line = res_json.get("response", "").strip().strip("1234567890.、- *\"'")
                            if len(clean_line) > 2:
                                self.generated_data.append({"text": clean_line, "intent": current_labels})
                                self.success_count += 1
                                if self.success_count <= 3:
                                    self.log(f"✔️ [{self.success_count}] {clean_line} {current_labels}")
                    except Exception as e:
                        continue

                # --- C. 結束處理 ---
                end_time = time.time()
                duration = end_time - start_time # 💡 計算總秒數

                if self.success_count > 0:
                    self.log(f"\n✅ 成功獲取 {self.success_count} 筆訓練資料！")
                    # 存檔時取選單第一個單字作為檔名
                    file_tag = selected_option.split(" ")[0]
                    self.log(f"\n✨ 生成完畢！耗時: {duration:.2f} 秒 (平均 {duration/self.success_count:.2f}s/筆)")
                    self.progress_label.configure(text=f"✅ 完成！總耗時: {int(duration)}s")
                    self.save_to_file(file_tag)

            # 無論哪種模式，最後都恢復按鈕
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

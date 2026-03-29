# python auto_packager.py
# 無塵環境打包器
import customtkinter as ctk
import tkinter.filedialog as fd
import threading
import subprocess
import os
import venv
import shutil

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class AutoPackagerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("無塵室自動打包機 📦")
        self.geometry("600x450")
        
        ctk.CTkLabel(self, text="無塵室自動打包機", font=("Arial", 24, "bold")).pack(pady=20)
        
        # 選擇檔案區
        self.file_frame = ctk.CTkFrame(self)
        self.file_frame.pack(pady=10, padx=20, fill="x")
        self.file_path_var = ctk.StringVar()
        ctk.CTkEntry(self.file_frame, textvariable=self.file_path_var, width=380, state="readonly").pack(side="left", padx=10, pady=10)
        ctk.CTkButton(self.file_frame, text="選擇 .py 檔案", command=self.select_file, width=100).pack(side="right", padx=10)
        
        # 輸入套件區
        self.pkg_frame = ctk.CTkFrame(self)
        self.pkg_frame.pack(pady=10, padx=20, fill="x")
        ctk.CTkLabel(self.pkg_frame, text="額外套件 (逗號隔開):").pack(side="left", padx=10, pady=10)
        self.pkg_entry = ctk.CTkEntry(self.pkg_frame, width=340, placeholder_text="例如: requests, pandas, customtkinter")
        self.pkg_entry.pack(side="right", padx=10)
        
        # 狀態 Log 區
        self.log_box = ctk.CTkTextbox(self, height=150)
        self.log_box.pack(pady=10, padx=20, fill="both", expand=True)
        
        # 一鍵打包按鈕
        self.pack_btn = ctk.CTkButton(self, text="🚀 一鍵無塵打包", command=self.start_packaging)
        self.pack_btn.pack(pady=10)

    def log(self, text):
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        
    def select_file(self):
        path = fd.askopenfilename(filetypes=[("Python Files", "*.py")])
        if path:
            self.file_path_var.set(path)
            
    def start_packaging(self):
        target_py = self.file_path_var.get()
        pkgs = self.pkg_entry.get()
        
        if not target_py:
            self.log("❌ 請先選擇要打包的 .py 檔案！")
            return
            
        self.pack_btn.configure(state="disabled", text="⏳ 正在無塵室施工中...")
        self.log("=============================")
        # 啟動執行緒，避免介面卡死
        threading.Thread(target=self.run_packaging, args=(target_py, pkgs), daemon=True).start()
        
    def run_packaging(self, target_py, pkgs):
        try:
            base_dir = os.path.dirname(target_py)
            # 在要打包的檔案旁邊建立一個暫時的虛擬環境資料夾
            env_dir = os.path.join(base_dir, "temp_clean_env")
            
            # 1. 建立虛擬環境 (內建 venv)
            self.log("🛠️ 步驟 1: 正在建立臨時無塵室...")
            venv.create(env_dir, with_pip=True)
            
            # 判斷系統並取得 pip 與 pyinstaller 的路徑
            if os.name == 'nt':
                pip_exe = os.path.join(env_dir, "Scripts", "pip.exe")
                pyinst_exe = os.path.join(env_dir, "Scripts", "pyinstaller.exe")
                # 隱藏 Windows 終端機彈跳視窗
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            else:
                pip_exe = os.path.join(env_dir, "bin", "pip")
                pyinst_exe = os.path.join(env_dir, "bin", "pyinstaller")
                startupinfo = None
                
            # 2. 安裝套件
            self.log("📦 步驟 2: 正在安裝 PyInstaller 與你指定的套件 (需要一點時間)...")
            pkg_list = ["pyinstaller"] + [p.strip() for p in pkgs.split(",") if p.strip()]
            subprocess.run([pip_exe, "install"] + pkg_list, check=True, startupinfo=startupinfo)
            
            # 3. 執行打包
            self.log("🚀 步驟 3: 開始編譯打包 (這會花比較久，請耐心等候)...")
            subprocess.run([
                pyinst_exe, 
                "--onefile", 
                "--windowed", 
                "--distpath", base_dir,  # 將 exe 直接產出到 .py 檔旁邊
                "--workpath", os.path.join(base_dir, "build"),
                target_py
            ], check=True, startupinfo=startupinfo)
            
            # 4. 清理垃圾
            self.log("🧹 步驟 4: 正在銷毀無塵室並清理施工垃圾...")
            shutil.rmtree(env_dir, ignore_errors=True)
            shutil.rmtree(os.path.join(base_dir, "build"), ignore_errors=True)
            spec_file = target_py.replace(".py", ".spec")
            if os.path.exists(spec_file):
                os.remove(spec_file)
                
            self.log("✅ 任務完成！你的輕量級執行檔已經誕生在旁邊了！")
            
        except Exception as e:
            self.log(f"❌ 發生錯誤: {str(e)}")
        finally:
            self.pack_btn.configure(state="normal", text="🚀 一鍵無塵打包")

if __name__ == "__main__":
    app = AutoPackagerApp()
    app.mainloop()
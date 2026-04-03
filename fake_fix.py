# fake_fix.py
import pandas as pd
import re
import os
import tkinter.filedialog as fd
import tkinter as tk

print("🕵️‍♂️ 啟動假資料自動檢查器...\n")

def check_suspicious_data(row):
    text = str(row['text'])
    intent = str(row['intent'])
    
    # 規則 1：如果是 MULTI_RECORD，但句子裡根本沒有「連接詞」或「兩個以上的數字」
    if intent == 'MULTI_RECORD':
        multi_markers = ['然後', '又', '加上', '順便', '還有', '另外']
        money_matches = re.findall(r'\d+', text)
        if not any(m in text for m in multi_markers) and len(money_matches) < 2:
            return "❌ 標記為 MULTI_RECORD，但缺乏連接詞或多筆金額"
            
    # 規則 2：如果是 SINGLE 意圖 (如 RECORD 或 ADVISOR)，卻出現多項式的特徵
    if intent in ['RECORD', 'ADVISOR', 'QUERY']:
        multi_markers = ['和', '與', '分別', '分配到', '比例']
        if any(m in text for m in multi_markers):
            return f"⚠️ 標記為 {intent} (單項)，但語句中含有多項分配字眼"
            
    # 規則 3：句子太短 (可能是瑕疵資料)
    if len(text) < 4:
        return "⚠️ 句子過短，可能無效"
        
    return "OK"

# 隱藏 tkinter 主視窗
root = tk.Tk()
root.withdraw()

print("請選擇你要檢查的 CSV 或 Excel 檔案...")
file_path = fd.askopenfilename(
    title="選擇要檢查的資料檔",
    filetypes=[("CSV files", "*.csv"), ("Excel files", "*.xlsx"), ("All files", "*.*")]
)

if not file_path:
    print("❌ 未選擇檔案，程式結束。")
    exit()

print(f"📂 正在讀取: {file_path}")

try:
    if file_path.endswith('.csv'):
        # 嘗試處理有 BOM 的 CSV
        df = pd.read_csv(file_path, encoding='utf-8-sig')
    else:
        df = pd.read_excel(file_path)

    if 'text' not in df.columns or 'intent' not in df.columns:
        print("❌ 錯誤：檔案必須包含 'text' 和 'intent' 兩個欄位！")
        exit()

    # 執行檢查
    df['check_result'] = df.apply(check_suspicious_data, axis=1)

    # 篩選出有問題的資料
    suspicious_df = df[df['check_result'] != "OK"]

    if len(suspicious_df) > 0:
        print(f"\n🚨 抓到了 {len(suspicious_df)} 筆可疑資料！")
        
        # 在終端機印出前幾筆
        for index, row in suspicious_df.head(10).iterrows():
            print(f"- [{row['intent']}] {row['text']} => {row['check_result']}")
        print("...")
        
        # 匯出成 Excel 讓你慢慢修改
        output_dir = os.path.dirname(file_path)
        output_file = os.path.join(output_dir, "需要人工修補的資料.xlsx")
        suspicious_df.to_excel(output_file, index=False)
        print(f"\n📁 已將可疑資料匯出至: {output_file}")
    else:
        print("\n✅ 太棒了！資料看起來很健康，沒有發現明顯異常！")

except Exception as e:
    print(f"❌ 發生錯誤: {e}")
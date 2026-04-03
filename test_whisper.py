# python test_whisper.py

import torch
from transformers import pipeline
import os
import warnings

# 🌟 加上這行，把煩人的舊語法警告全部屏蔽掉！
warnings.filterwarnings("ignore", category=UserWarning)

# 1. 自動偵測環境 (Windows GPU / Mac CPU 通用)
device = 0 if torch.cuda.is_available() else -1

# 2. 初始化 Pipeline
pipe = pipeline(
    "automatic-speech-recognition",
    model="openai/whisper-small",
    device=device,
    # 這裡的 torch_dtype 已經被官方棄用，改成 dtype
    model_kwargs={"dtype": torch.float16 if device == 0 else torch.float32}
)

def run_transcription(file_path: str):
    if not os.path.exists(file_path):
        print(f"❌ 找不到檔案: {file_path}")
        return

    # 檢查是否為 .m4a 格式
    is_m4a = file_path.lower().endswith(".m4a")

    print(f"--- 執行環境: {'GPU 加速' if device == 0 else 'CPU 模式'} ---")
    print(f"正在辨識: {os.path.basename(file_path)}...")

    try:
        # 3. 執行辨識
        raw_result = pipe(
            file_path,
            generate_kwargs={"language": "chinese", "task": "transcribe"}
        )

        # 4. 解決紅線問題 (用最簡單的判斷)
        if isinstance(raw_result, dict):
            text_result = raw_result.get("text", "")
        else:
            text_result = ""

        # 5. 結果判斷與提示
        if not text_result.strip():
            if is_m4a:
                print("\n⚠️ 辨識結果為空。由於您使用的是 .m4a 格式，若格式特殊可能導致讀取失敗，建議先轉為 .wav 再試。")
            else:
                print("\n⚠️ 辨識結果為空，請檢查音檔內容是否有聲音。")
        else:
            print("\n[聽寫結果]:")
            print(text_result)

    except Exception as e:
        print(f"\n❌ 程式發生錯誤: {e}")
        if is_m4a:
            print("💡 偵測到您使用 .m4a 格式，這可能是造成錯誤的原因，請嘗試將檔案轉為 .wav 格式。")

    print("-" * 30)

if __name__ == "__main__":
    audio_path = "web_app/temp/test.wav" # 這裡可以改成你的 .m4a 測試看看
    run_transcription(audio_path)

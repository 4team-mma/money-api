import torch
from transformers import pipeline

# 1. 初始化語音辨識管線 (載入 openai/whisper-small 模型)
# 如果你有獨立顯卡 (Nvidia)，device=0 可以用 GPU 跑，沒有的話填 -1 用 CPU 跑
pipe = pipeline(
    "automatic-speech-recognition",
    model="openai/whisper-small",
    device=-1 # 如果有 GPU 請改為 0
)

# 2. 準備一個測試用的音檔 (wav 或 mp3)
# 🌟 這裡改成你剛剛建立的 temp 資料夾路徑
audio_path = "web_app/temp/test_audio.wav" 

# 3. 進行推論 (Inference)
print("模型正在聽...")
result = pipe(audio_path, generate_kwargs={"language": "chinese"})

print("聽寫結果：")
print(result["text"])
# web_app/services/groq_service.py
from groq import AsyncGroq
import logging
import os

logger = logging.getLogger(__name__)

class GroqService:
    @staticmethod
    async def chat_async(api_key: str, model_id: str, prompt: str, system_instruction: str):
        """同步呼叫 Groq API 的非同步封裝"""
        try:
            client = AsyncGroq(api_key=api_key)
            response = await client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}
                ],
                model=model_id,
                temperature=0.7,
                max_tokens=1024,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"❌ Groq API Error: {str(e)}")
            raise e
        
        
    # 🌟 新增：專屬的語音辨識非同步函式
    @staticmethod
    async def transcribe_audio_async(api_key: str, file_path: str) -> str:
        """接收音檔路徑，呼叫 Groq Whisper 轉成文字"""
        try:
            client = AsyncGroq(api_key=api_key)
            
            # 打開音檔並上傳給 Groq
            with open(file_path, "rb") as file:
                # 使用 Whisper large v3 turbo，速度最快、支援多國語言
                transcription = await client.audio.transcriptions.create(
                    file=(os.path.basename(file_path), file.read()), # 必須給檔名和二進位內容
                    model="whisper-large-v3-turbo", 
                    language="zh", # 指定中文，辨識會更精準
                    response_format="text"
                )
            return transcription.text
        except Exception as e:
            logger.error(f"❌ Groq Whisper API Error: {str(e)}")
            raise e
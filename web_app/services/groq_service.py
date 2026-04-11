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
            
            with open(file_path, "rb") as file:
                transcription = await client.audio.transcriptions.create(
                    file=(os.path.basename(file_path), file.read()),
                    model="whisper-large-v3-turbo", 
                    language="zh",
                    response_format="text" # 🌟 確保它直接給我們純文字
                )
            
            # 🌟 終極防呆：不管 SDK 給字串還是物件，我們都處理！
            if isinstance(transcription, str):
                return transcription # 如果已經是字串，直接回傳
            else:
                return transcription.text # 如果是物件，才抽出 text 屬性

        except Exception as e:
            logger.error(f"❌ Groq Whisper API Error: {str(e)}")
            raise e
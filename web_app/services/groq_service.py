# web_app/services/groq_service.py
from groq import AsyncGroq
import logging

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
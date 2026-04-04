import os
import json
import numpy as np
import jieba
import onnxruntime as ort
import re
from typing import Optional, Dict, List
from web_app.services.vector_db_tools import VectorDBTools

class FinanceAgentMixAIService:
    # 🌟 完全去 Pickle 化：改用 Dict 和 List 存儲
    word_index: Optional[Dict[str, int]] = None
    label_list: Optional[List[str]] = None
    ort_session: Optional[ort.InferenceSession] = None
    maxlen: int = 40

    MODEL_DIR = os.path.join(os.getcwd(), "web_app", "models", "checkpoints")

    @classmethod
    def _lazy_load(cls):
        """確保模型與配置只會載入一次，並自動適應 V1/V2"""
        if cls.word_index is None or cls.label_list is None or cls.ort_session is None:
            try:
                # 🌟 [新增在這]：載入與模型同資料夾的強化詞庫
                user_dict_path = os.path.join(cls.MODEL_DIR, "user_dict.txt")
                if os.path.exists(user_dict_path):
                    jieba.load_userdict(user_dict_path)
                    print(f"📚 [Jieba] 外部強化詞庫載入成功：{user_dict_path}")
                else:
                    print(f"⚠️ [Jieba] 找不到詞庫檔 {user_dict_path}，斷詞精準度可能會下降喵！")

                # 2. 載入模型與字典 (路徑對齊你截圖中的檔名)
                dict_path = os.path.join(cls.MODEL_DIR, "tokenizer_dict.json")
                label_path = os.path.join(cls.MODEL_DIR, "label_map.json")
                onnx_path = os.path.join(cls.MODEL_DIR, "cupid_intent_model.onnx")

                with open(dict_path, 'r', encoding='utf-8') as f:
                    cls.word_index = json.load(f)
                with open(label_path, 'r', encoding='utf-8') as f:
                    cls.label_list = json.load(f)

                cls.ort_session = ort.InferenceSession(onnx_path)
                print("🚀 [MixAIService] 初始化成功！")

            except Exception as e:
                print(f"❌ 載入失敗: {e}")
                raise e

    @classmethod
    def _manual_texts_to_sequences(cls, text: str, maxlen: int = 40):
        """
        手寫輕量化轉換邏輯。
        將字串轉為數字序列，並進行 Post-padding。
        """
        assert cls.word_index is not None
        tokens = text.split()
        # ⚠️ 修正點：只保留字典裡有的字，沒有的直接忽略，不要塞 0
        sequence = []
        for word in tokens:
            if word in cls.word_index:
                sequence.append(cls.word_index[word])

        padded = np.zeros((1, maxlen), dtype=np.float32)
        if sequence:
            trunc = sequence[:maxlen]
            padded[0, :len(trunc)] = trunc
        return padded

    @classmethod
    def analyze_intent(cls, message: str):
        # 0. 確保資源已載入
        cls._lazy_load()
        assert cls.word_index is not None
        assert cls.label_list is not None
        assert cls.ort_session is not None

        text_str = str(message)

        # 1. 預處理：斷詞 + 轉序列 + Padding
        cut_text = " ".join(jieba.cut(text_str))
        padded_seq = cls._manual_texts_to_sequences(cut_text, maxlen=cls.maxlen)

        # 2. ONNX 模型推論
        input_name = cls.ort_session.get_inputs()[0].name
        raw_probs = cls.ort_session.run(None, {input_name: padded_seq})[0]
        probs = np.array(raw_probs)

        # 3. 取得模型直覺 (使用 label_list 取代 encoder)
        best_idx = int(np.argmax(probs, axis=1)[0])
        confidence = float(probs[0][best_idx])
        keras_intent = cls.label_list[best_idx]

        # 4. 執行 V10 行為邏輯攔截器修正
        final_intent = cls.apply_v10_logic(text_str, keras_intent)

        return {
            "predicted_intent": keras_intent,
            "final_intent": final_intent,
            "confidence": confidence
        }

    @classmethod
    def apply_v10_logic(cls, text_str, keras_intent):
        """邱比特行為邏輯攔截器 V10 (統一變數與關鍵字版本)"""

        # 🛡️ 1. 向量警衛室優先
        vector_intent = VectorDBTools.search_intent(text_str)
        if vector_intent is not None:
            return vector_intent

        final_intent = keras_intent
        
        # 提前把這幾個常用變數算好，後面大家一起用
        digit_groups = re.findall(r'\d+', text_str)
        money_unit_count = text_str.count('元') + text_str.count('塊') + text_str.count('千') + text_str.count('萬')
        record_trigger_words = ['存', '領', '花', '賺', '薪水', '支出', '買', '付', '收', '匯', '轉帳', '轉給', '轉到', '轉出', '轉入', '轉']
        

        # 🚀 2. [絕對法則 - 查詢攔截]
        query_hard_keywords = ['有沒有', '吃過', '買過', '紀錄', '查一下', '找一下', '過嗎']
        if any(k in text_str for k in query_hard_keywords):
            final_intent = 'QUERY'

        # 🔥 3. 強制升級為 RECORD (攔截 ONNX 的 CHAT 誤判)
        if final_intent == 'CHAT' and len(digit_groups) > 0 and any(k in text_str for k in record_trigger_words):
            final_intent = 'RECORD'
            print("🛡️ [V10 攔截] 偵測到數字與交易動詞，強制將 CHAT 升級為 RECORD")

        # 🚨 4. [絕對法則 - RECORD 降級認定]
        if final_intent in ['RECORD', 'MULTI_RECORD']:
            # 💡 修正點：只要「完全沒有數字」且「沒有金額單位」，不管有沒有提到存/花，通通降級為 CHAT！
            # (完美防禦：「我存好多錢，好開心」 -> 降級為 CHAT)
            if len(digit_groups) == 0 and money_unit_count == 0:
                return 'CHAT'

        # 🛡️ 5. [絕對法則 - QUERY 降級認定 (新增)]
        if final_intent in ['QUERY', 'MULTI_QUERY']:
            query_verify_words = ['多少', '錢', '查', '總共', '剩', '明細', '算', '嗎', '？', '?']
            # 💡 修正點：如果是 QUERY，但一句話裡面「沒有數字」且「沒有疑問詞或錢的關鍵字」
            # (完美防禦：「你要上班嗎」被 ONNX 誤判成 QUERY -> 降級為 CHAT)
            if len(digit_groups) == 0 and not any(q in text_str for q in query_verify_words):
                return 'CHAT'

        # 📚 4. 純知識名詞保護
        knowledge_keywords = ['任務', '成就', '主題', '背景', '解鎖', '手冊', '規則', '簽到', '卡牌', 'CPI', '物價指數']
        if any(kw in text_str for kw in knowledge_keywords):
            if any(kw in text_str for kw in ['好簡單', '太難了', '真累', '開心', '好開心', '早上好', '嗚嗚']):
                return 'CHAT'
            if any(m in text_str for m in ['順便', '又', '加上', '然後', '之外', '還有']):
                return 'MULTI_KNOWLEDGE'
            return 'KNOWLEDGE'

        return final_intent

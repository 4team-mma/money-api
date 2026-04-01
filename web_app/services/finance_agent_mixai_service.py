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
    
    MODEL_DIR = os.path.join(os.getcwd(), "web_app", "models", "checkpoints")

    @classmethod
    def _lazy_load(cls):
        """確保模型與兩份 JSON 配置只會載入一次"""
        if cls.word_index is None or cls.label_list is None or cls.ort_session is None:
            try:
                dict_path = os.path.join(cls.MODEL_DIR, "tokenizer_dict.json")
                label_path = os.path.join(cls.MODEL_DIR, "label_map.json")
                onnx_path = os.path.join(cls.MODEL_DIR, "cupid_intent_model.onnx")

                # 1. 載入文字字典 (Tokenizer)
                with open(dict_path, 'r', encoding='utf-8') as f:
                    cls.word_index = json.load(f)
                
                # 2. 載入標籤對照表 (Label Encoder)
                with open(label_path, 'r', encoding='utf-8') as f:
                    cls.label_list = json.load(f)
                
                # 3. 啟動 ONNX 推論引擎
                cls.ort_session = ort.InferenceSession(onnx_path)
                
                print("🚀 [究極輕量版] ONNX引擎與雙核心JSON配置載入成功！(零環境依賴)")
            except Exception as e:
                print(f"❌ [MixAIService] 載入資源失敗: {e}")
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
        padded_seq = cls._manual_texts_to_sequences(cut_text, maxlen=40)
        
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
        """邱比特行為邏輯攔截器 V10 (ChromaDB 向量進化 + 絕對法則防護)"""
        
        # 🛡️ 1. 啟動向量警衛室
        vector_intent = VectorDBTools.search_intent(text_str)
        if vector_intent is not None:
            print(f"🛡️ [向量警衛室] 攔截成功！覆蓋模型直覺: {keras_intent} -> {vector_intent}")
            return vector_intent

        print(f"🤖 [ONNX模型] 警衛室放行，使用模型直覺: {keras_intent}")
        final_intent = keras_intent
        
        # ==========================================
        # 🚀 這裡新增：[絕對法則 - 查詢攔截]
        # 即使模型直覺是 CHAT，只要命中這些「有沒有、紀錄」關鍵字，強制變 QUERY
        # ==========================================
        query_hard_keywords = ['有沒有', '吃過', '買過', '紀錄', '查一下', '找一下', '過嗎']
        if any(k in text_str for k in query_hard_keywords):
            print(f"🚨 [絕對法則] 偵測到事實查詢關鍵字！強制轉換為 QUERY")
            return 'QUERY'
        
        # ==========================================
        # 🚨 2. [絕對法則]：沒錢就不能記帳！(解決「買台積電爽啦」痛點)
        # ==========================================
        if final_intent in ['RECORD', 'MULTI_RECORD']:
            # 抓取句子裡的阿拉伯數字，或是「元、塊、萬」等明確單位
            digit_groups = re.findall(r'\d+', text_str)
            money_unit_count = text_str.count('元') + text_str.count('塊') + text_str.count('千') + text_str.count('萬')
            
            # 如果完全沒有數字，也沒有錢的單位，代表只是在講幹話或分享心情
            if len(digit_groups) == 0 and money_unit_count == 0:
                print("🚨 [絕對法則] 發現沒有具體金額！強制將 RECORD 降級為 CHAT")
                return 'CHAT'

        # ==========================================
        # 📚 3. 純知識名詞保護
        # ==========================================
        knowledge_keywords = ['任務', '成就', '主題', '背景', '解鎖', '手冊', '規則', '簽到', '卡牌', 'CPI', '物價指數']
        if any(kw in text_str for kw in knowledge_keywords):
            if any(kw in text_str for kw in ['好簡單', '太難了', '真累', '開心', '好開心', '早上好', '嗚嗚']):
                return 'CHAT'
            multi_markers = ['順便', '又', '加上', '然後', '之外', '還有']
            if any(m in text_str for m in multi_markers):
                return 'MULTI_KNOWLEDGE'
            return 'KNOWLEDGE'

        return final_intent
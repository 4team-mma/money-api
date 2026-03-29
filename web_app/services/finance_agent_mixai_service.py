import os
import json
import numpy as np
import jieba
import onnxruntime as ort
import re
from typing import Any, Optional, Dict, List

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
        # 將字轉為 index，字典找不到則給 0 (OOV)
        sequence = [cls.word_index.get(word, 0) for word in tokens]
        
        # 固定長度的 Padding
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
        """邱比特行為邏輯攔截器 V10 - 究極進化版"""
        action_keywords = ['買', '花', '吃', '喝', '給', '拿', '領', '存', '記', '付', '收', '入']
        action_count = sum(1 for kw in action_keywords if kw in text_str)

        digit_groups = re.findall(r'\d+', text_str)
        money_unit_count = text_str.count('元') + text_str.count('塊')
        money_strength = max(money_unit_count, len(digit_groups))

        # 1. 建議攔截
        if any(kw in text_str for kw in ['建議', '該怎麼', '該怎', '還是', '如何做好', '怎麼做']):
            return 'ADVISOR'

        # 2. 查詢攔截
        query_triggers = ['多少', '剩多少', '還剩', '預算炸了', '會不會', '查一下', '清單', '明細', '統計']
        if any(kw in text_str for kw in query_triggers):
            query_targets = sum(1 for kw in ['開銷', '收入', '餘額', '預算', '支出', '資產'] if kw in text_str)
            if query_targets >= 2 or any(kw in text_str for kw in ['還有', '順便', '和']):
                return 'MULTI_QUERY'
            return 'QUERY'

        # 3. 閒聊與意圖降級攔截
        emotion_keywords = ['到底要不要', '哈哈', '送給你', '好開心', '呢', '傷心', '嗚嗚']
        if any(kw in text_str for kw in emotion_keywords):
            record_actions = ['存', '記', '買', '花', '支', '付', '收', '入', '領']
            has_real_action = any(kw in text_str for kw in record_actions)

            if '到底要不要' in text_str or '呢' in text_str or '嗎' in text_str:
                if not has_real_action: return 'CHAT'
            if keras_intent in ['RECORD', 'MULTI_RECORD'] and (money_strength >= 1 or has_real_action):
                return keras_intent
            if money_strength == 0 and not has_real_action:
                return 'CHAT'

        # 4. 多筆判定
        is_multi_record = False
        multi_markers = ['順便', '又', '加上', '然後', '之外', '還有', '第一', '第二']
        if money_strength >= 2:
            if action_count >= 2 or any(m in text_str for m in multi_markers):
                is_multi_record = True

        final_intent = keras_intent
        if is_multi_record:
            if 'KNOWLEDGE' in final_intent: final_intent = 'MULTI_KNOWLEDGE'
            elif 'QUERY' in final_intent: final_intent = 'MULTI_QUERY'
            else: final_intent = 'MULTI_RECORD'
        elif final_intent == 'RECORD':
            if money_strength == 0 and action_count == 0:
                final_intent = 'CHAT'

        # 5. 知識庫保護
        knowledge_keywords = ['任務', '成就', '主題', '背景', '解鎖', '手冊', '規則', 'CPI', '卡牌', '物價指數']
        if any(kw in text_str for kw in knowledge_keywords):
            if any(kw in text_str for kw in ['好簡單', '太難了', '真累', '開心', '早上好']):
                return 'CHAT'
            if any(m in text_str for m in multi_markers):
                return 'MULTI_KNOWLEDGE'
            return 'KNOWLEDGE'

        return final_intent
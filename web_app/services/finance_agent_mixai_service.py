import os
import json
import numpy as np
import jieba
import onnxruntime as ort

from typing import Optional, Dict, List
from web_app.services.vector_db_tools import VectorDBTools

from ..services.nlp.context import IntentContext
from ..services.nlp.engine import RuleEngine
# from ..services.nlp.patterns import INTENT_PATTERNS
# from ..services.nlp.rules import INTENT_RULES

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
                    print(f"📚 [Jieba] ：{user_dict_path}")
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
        # 0. 初始化
        cls._lazy_load()
        assert cls.ort_session is not None
        assert cls.label_list is not None
        text_str = str(message).strip()

        # ---------------------------------------------------------
        # 🛡️ 第一道防線：ChromaDB 向量警衛室 (VectorDBTools)
        # ---------------------------------------------------------
        # 如果使用者說過的話完全命中資料庫，直接 100% 回傳結果，不跑後面的邏輯
        vector_intent = VectorDBTools.search_intent(text_str)
        if vector_intent is not None:
            print(f"👮‍♂️ [第一道防線] 向量庫直接命中: {vector_intent}")
            return {
                "predicted_intent": vector_intent, 
                "final_intent": vector_intent,
                "confidence": 1.0 
            }

        # ---------------------------------------------------------
        # 🥈 第二道防線：ONNX 模型推論 (直覺判斷)
        # ---------------------------------------------------------
        cut_text = " ".join(jieba.cut(text_str))
        padded_seq = cls._manual_texts_to_sequences(cut_text, maxlen=cls.maxlen)
        
        input_name = cls.ort_session.get_inputs()[0].name
        raw_probs = cls.ort_session.run(None, {input_name: padded_seq})[0]
        probs = np.array(raw_probs)

        best_idx = int(np.argmax(probs, axis=1)[0])
        confidence = float(probs[0][best_idx])
        keras_intent = cls.label_list[best_idx]

        # ---------------------------------------------------------
        # 🥉 第三道防線：NLP 跑分引擎 (Logical Correctness)
        # ---------------------------------------------------------
        # 重構的「兩階段決策引擎」，負責修正 ONNX 的錯誤
        final_intent = cls.apply_v10_logic(text_str, keras_intent, confidence)

        return {
            "predicted_intent": keras_intent,
            "final_intent": final_intent,
            "confidence": confidence
        }

    @classmethod
    def apply_v10_logic(cls, text_str, keras_intent, confidence):
        # 1. 建立上下文，傳入 ONNX 的預測結果與信心度
        ctx = IntentContext(text_str, keras_intent, confidence)

        # 2. 啟動跑分引擎
        ctx = RuleEngine.apply(ctx)

        # 3. 診斷日誌 
        if ctx.trace:
            print(f"📊 [NLP 診斷] {text_str} -> {ctx.intent} | 軌跡: {ctx.trace}")
        
        return ctx.intent
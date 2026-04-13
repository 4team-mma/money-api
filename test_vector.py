

import math
from web_app.services.vector_db_tools import VectorDBTools

# 1. 呼叫你的地端引擎 (nomic-embed-text)
local_embedder = VectorDBTools._get_local_embeddings()

# 2. 隨便輸入一句話產生向量
vector = local_embedder.embed_query("測試一下喵！看你有沒有被正規化！")

# 3. 計算這個向量的長度 (歐幾里德長度公式：把每個數字平方相加，再開根號)
length = math.sqrt(sum([x**2 for x in vector]))

print(f"向量長度是: {length}")
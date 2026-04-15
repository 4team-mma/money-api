from typing import Annotated, Literal
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq
import os

# ==========================================
# 1. 定義 Tools (請組員把分析邏輯寫在這裡)
# ==========================================
@tool
def get_monthly_summary(user_id: int) -> str:
    """查詢使用者本月的總收入、總支出與結餘。理財分析前必須先呼叫此工具。"""
    # 這裡放連接資料庫的邏輯
    return f"[系統回傳] user_{user_id} 本月總支出: 15000元, 總收入: 50000元"

@tool
def detect_spending_anomalies(user_id: int) -> str:
    """偵測使用者近期的消費是否有異常暴增 (Z-score 分析)。"""
    # 這裡放組員的數據分析邏輯
    return f"[系統回傳] 偵測到『娛樂類』支出異常偏高。"

# 將工具打包
tools = [get_monthly_summary, detect_spending_anomalies]

# ==========================================
# 2. 定義狀態 (State) 與 LLM
# ==========================================
# 定義對話紀錄的狀態 (MessagesState 是 LangGraph 內建最常用的狀態)
class State(TypedDict):
    messages: Annotated[list, add_messages]

# 初始化 LLM 並綁定工具 (讓 LLM 知道它有哪些工具可以用)
llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.2)
llm_with_tools = llm.bind_tools(tools)

# ==========================================
# 3. 定義圖形節點 (Nodes)
# ==========================================
def chatbot_node(state: State):
    """思考與決策節點：LLM 決定要回答還是要呼叫工具"""
    # 掛載 Advisor 人格設定
    sys_msg = SystemMessage(content="你是 MoneyMMA 的專業理財顧問。請善用工具分析使用者財務狀況後，給予溫暖、專業的建議。")
    messages = [sys_msg] + state["messages"]
    
    # LLM 進行推論
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

# ==========================================
# 4. 組裝 LangGraph (The Graph)
# ==========================================
# 初始化狀態機
graph_builder = StateGraph(State)

# 加入節點：大腦(chatbot_node) 與 工具箱(ToolNode)
graph_builder.add_node("chatbot", chatbot_node)
graph_builder.add_node("tools", ToolNode(tools=tools)) # ToolNode 是官方提供的方便工具執行器

# 定義流程路線 (Edges)
graph_builder.add_edge(START, "chatbot")

# 條件路由：如果大腦說要用工具 -> 走 tools 節點；如果大腦直接給出文字建議 -> 結束 (END)
graph_builder.add_conditional_edges(
    "chatbot",
    tools_condition, # 官方內建的判斷條件：檢測 LLM 回覆中有沒有 tool_calls
)

# 工具執行完後，把結果丟回給大腦繼續思考
graph_builder.add_edge("tools", "chatbot")

# 最終編譯成可執行的應用
advisor_graph = graph_builder.compile()

# ==========================================
# 5. 給外部呼叫的進入點
# ==========================================
async def analyze_finance_advice(user_id: int, user_message: str):
    """被原本路由器呼叫的主要 Function"""
    # 這裡可以把 user_id 偷偷塞進去，限制 Agent 只能查該用戶的資料
    prompt = f"(背景參數 user_id={user_id}) 使用者詢問：{user_message}"
    
    # 執行圖形
    result = await advisor_graph.ainvoke({"messages": [("user", prompt)]})
    
    # 取出最後一句話回傳給前端
    return result["messages"][-1].content
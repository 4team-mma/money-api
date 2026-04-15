# web_app/services/advisor_graph_service.py
import json
import re
from typing import Annotated
from typing_extensions import TypedDict
from sqlalchemy.orm import Session

from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq

# 💡 小白教學區：把我們需要的資料庫模型和隊友寫好的功能「進口」進來
from web_app.models.models import Member
from web_app.routes.analysis import get_cpi_comparison, get_salary_comparison

# ==========================================
# 1. 定義狀態 (State)
# ==========================================
class State(TypedDict):
    messages: Annotated[list, add_messages]

# ==========================================
# 2. 閉包工廠 (把 db 跟 current_user 鎖進房間)
# ==========================================
def create_advisor_graph(db: Session, current_user: Member):
    """
    這是一個「工廠函數」。
    每當有使用者發問，我們就動態建立一個全新的 Graph，
    並且把這個使用者的資料庫連線 (db) 和身分 (current_user) 傳進來給 Tool 用。
    """
    
    # ------------------------------------------
    # 🛠️ 工具一：CPI 物價比對 Tool
    # ------------------------------------------
    @tool
    def tool_get_cpi_comparison(year: str, month: str) -> str:
        """
        [重要提示給 LLM]：當使用者詢問「物價是不是變貴了」、「這個月花費合理嗎」、「通膨」等問題時，請呼叫此工具。
        參數說明：
        - year: 四碼年份字串，例如 "2026"
        - month: 兩碼月份字串，例如 "04"
        """
        try:
            # 🛡️ 神級防禦：把 LLM 亂傳的 "2026年" 變 "2026"，"4月" 或 "4" 變成 "04"
            clean_year = re.sub(r'\D', '', str(year))
            clean_month = re.sub(r'\D', '', str(month)).zfill(2)

            result_list = get_cpi_comparison(
                year=clean_year, 
                month=clean_month, 
                db=db, 
                current_user=current_user
            )
            return json.dumps(result_list, ensure_ascii=False)
        except Exception as e:
            return f"獲取 CPI 資料失敗：{str(e)}"

    # ------------------------------------------
    # 🛠️ 工具二：薪資基準比對 Tool
    # ------------------------------------------
    @tool
    def tool_get_salary_benchmark(year: str, month: str) -> str:
        """
        [重要提示給 LLM]：當使用者詢問「我的薪水算高嗎」、「我是不是薪水太低」、「跟同行比起來如何」時，請呼叫此工具。
        參數說明：
        - year: 四碼年份字串，例如 "2026"
        - month: 兩碼月份字串，例如 "04"
        """
        try:
            # 🛡️ 同理，加上神級防禦
            clean_year = re.sub(r'\D', '', str(year))
            clean_month = re.sub(r'\D', '', str(month)).zfill(2)

            result_dict = get_salary_comparison(
                year=clean_year, 
                month=clean_month, 
                db=db, 
                current_user=current_user
            )
            return json.dumps(result_dict, ensure_ascii=False)
        except Exception as e:
            return f"獲取薪資比較資料失敗：{str(e)}"

    # 把工具打包成一個列表
    tools = [tool_get_cpi_comparison, tool_get_salary_benchmark]

    # ------------------------------------------
    # 🧠 初始化 LLM (大腦)
    # ------------------------------------------
    llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.2)
    llm_with_tools = llm.bind_tools(tools)

    # ------------------------------------------
    # 🤖 定義決策節點
    # ------------------------------------------
    def chatbot_node(state: State):
        # 💡 動態把使用者的名字塞進 Prompt 裡，讓喵喵更有親切感！
        sys_prompt = f"""
        你是 MoneyMMA 的專業理財喵喵顧問。現在正在為小主人「{current_user.name}」服務。
        請善用你的工具（CPI 比對、薪資比對）來獲取真實數據，再給予溫暖、專業的理財建議。
        回答結尾請記得加上「喵！」。
        """
        messages = [SystemMessage(content=sys_prompt)] + state["messages"]
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    # ------------------------------------------
    # 🕸️ 組裝 Graph (畫出流程圖)
    # ------------------------------------------
    graph_builder = StateGraph(State)
    graph_builder.add_node("chatbot", chatbot_node)
    graph_builder.add_node("tools", ToolNode(tools=tools)) 
    
    graph_builder.add_edge(START, "chatbot")
    graph_builder.add_conditional_edges("chatbot", tools_condition)
    graph_builder.add_edge("tools", "chatbot")
    
    return graph_builder.compile()

# ==========================================
# 3. 給外部 API (Router) 呼叫的進入點
# ==========================================
async def analyze_finance_advice(user_message: str, db: Session, current_user: Member):
    """
    這支 Function 是給你主要的 FastAPI 路由呼叫的。
    你需要把前端傳來的 user_message、資料庫 db、跟 current_user 傳進來。
    """
    # 1. 建立當次對話專屬的 Graph
    advisor_graph = create_advisor_graph(db, current_user)
    
    # 2. 執行圖形推理
    result = await advisor_graph.ainvoke({"messages": [("user", user_message)]})
    
    # 3. 取出最後一句話回傳給前端
    return result["messages"][-1].content
# web_app/services/advisor_graph_service.py
import json
import re
import asyncio

# 🌟 新增 cast，用來安撫 Pylance 的嚴格型別檢查
from typing import Annotated, Optional, cast
from typing_extensions import TypedDict
from sqlalchemy.orm import Session

from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import MemorySaver

# 進口資料庫模型與隊友功能
from web_app.models.models import Member
from web_app.routes.analysis import get_cpi_comparison, get_salary_comparison
from web_app.services.advisor_tools import FinancialAdvisorService
from web_app.prompts.ai_analysis_prompts import SYSTEM_INSTRUCTION

# ==========================================
# 1. 定義狀態 (State)
# ==========================================
class State(TypedDict):
    messages: Annotated[list, add_messages]

# ==========================================
# 2. 全域工具定義 (使用 RunnableConfig 拿取 db 與 user)
# ==========================================

@tool
async def tool_get_cpi_comparison(year: str, month: str, config: RunnableConfig) -> str:
    """
    [重要提示給 LLM]：當使用者詢問「物價是不是變貴了」、「這個月花費合理嗎」、「通膨」等問題時，請呼叫此工具。
    """
    # 🛡️ 使用 cast 明確告訴 Pylance 型別，消除紅線
    configurable = config.get("configurable", {})
    db = cast(Session, configurable.get("db"))
    current_user = cast(Member, configurable.get("current_user"))
    
    try:
        clean_year = re.sub(r'\D', '', str(year))
        clean_month = re.sub(r'\D', '', str(month)).zfill(2)

        result_list = await asyncio.to_thread(
            get_cpi_comparison, 
            year=clean_year, 
            month=clean_month, 
            db=db, 
            current_user=current_user
        )
        return json.dumps(result_list, ensure_ascii=False)
    except Exception as e:
        return f"獲取 CPI 資料失敗：{str(e)}"


@tool
async def tool_get_salary_benchmark(year: str, month: str, config: RunnableConfig, industry: Optional[str] = None) -> str:
    """
    [重要提示給 LLM]：當使用者詢問「我的薪水算高嗎」、「我是不是薪水太低」、「跟同行比起來如何」時呼叫。
    """
    configurable = config.get("configurable", {})
    db = cast(Session, configurable.get("db"))
    current_user = cast(Member, configurable.get("current_user"))
    
    try:
        clean_year = re.sub(r'\D', '', str(year))
        clean_month = re.sub(r'\D', '', str(month)).zfill(2)

        result_dict = await asyncio.to_thread(
            get_salary_comparison, 
            year=clean_year, 
            month=clean_month, 
            industry=industry,
            db=db, 
            current_user=current_user
        )
        return json.dumps(result_dict, ensure_ascii=False)
    except Exception as e:
        return f"獲取薪資比較資料失敗：{str(e)}"


@tool
async def tool_get_advanced_anomaly_analysis(config: RunnableConfig) -> str:
    """
    [進階診斷]：當使用者詢問「為什麼我最近存不到錢」、「我的消費正常嗎」或感覺「焦慮」時呼叫。
    """
    configurable = config.get("configurable", {})
    db = cast(Session, configurable.get("db"))
    current_user = cast(Member, configurable.get("current_user"))
    
    try:
        context = await FinancialAdvisorService.get_ai_context(db, current_user)
        anomaly = context['metrics']['anomaly_analysis']
        
        report = {
            "is_anomaly": anomaly['is_anomaly'],
            "z_score": anomaly['z_score'],
            "severity": anomaly['severity'],
            "status_desc": "顯著異常" if anomaly['is_anomaly'] else "正常波動"
        }
        return json.dumps(report, ensure_ascii=False)
    except Exception as e:
        return f"異常偵測執行失敗：{str(e)}"


@tool
async def tool_get_global_financial_overview(config: RunnableConfig) -> str:
    """
    [全局概覽]：當使用者詢問「我現在有多少錢」、「這個月支出多少」、「消費占比」或「整體分析」時呼叫。
    """
    configurable = config.get("configurable", {})
    db = cast(Session, configurable.get("db"))
    current_user = cast(Member, configurable.get("current_user"))
    
    try:
        context = await FinancialAdvisorService.get_ai_context(db, current_user)
        metrics = context['metrics']
        top_cats = context['top_categories']
        
        overview = {
            "使用者名稱": context['user_profile']['name'],
            "職業": context['user_profile']['job'],
            "本月總支出": f"NT$ {metrics['total_expense']:,}",
            "支出變動率": metrics['growth_from_last_month'],
            "當前淨資產": f"NT$ {metrics['current_net_worth']:,}",
            "前三大消費占比": [f"{i['category']}({i['ratio']}%)" for i in top_cats]
        }
        return json.dumps(overview, ensure_ascii=False)
    except Exception as e:
        return f"全局數據獲取失敗：{str(e)}"

# 打包所有工具
tools = [
    tool_get_cpi_comparison, 
    tool_get_salary_benchmark, 
    tool_get_advanced_anomaly_analysis, 
    tool_get_global_financial_overview
]

# ------------------------------------------
# 🧠 全域初始化 LLM
# ------------------------------------------
llm = ChatGroq(model="meta-llama/llama-4-scout-17b-16e-instruct", temperature=0.2)
llm_with_tools = llm.bind_tools(tools)

# ------------------------------------------
# 🤖 定義決策節點 (Chatbot Node)
# ------------------------------------------
def chatbot_node(state: State, config: RunnableConfig):
    # 🛡️ 這裡也要加上 cast 避免 current_user.name 報錯
    configurable = config.get("configurable", {})
    current_user = cast(Member, configurable.get("current_user"))
    
    from datetime import datetime
    now = datetime.now()
    current_year = now.strftime("%Y")
    current_month = now.strftime("%m")

    # 🛡️ 絕對防禦 Token 暴增：切片法
    # state["messages"] 裡面存了從頭到尾的所有對話
    # 我們只取最後 6 條 (約等於最近的 3 次一問一答)
    recent_messages = state["messages"][-6:] 
    
    # 把舊的 SystemMessage 洗掉，只保留最新的一次
    clean_messages = [msg for msg in recent_messages if not isinstance(msg, SystemMessage)]

    full_sys_prompt = f"""
    {SYSTEM_INSTRUCTION}
    
    現在正在為小主人「{current_user.name}」進行深度財務諮詢。
    [系統當前時間]：{current_year} 年 {current_month} 月。
    
    【操作準則】：
    1. 若使用者詢問具體數據，請優先使用『全局財務視角整合工具』。
    2. 若使用者感到不安或數據異常，請使用『進階分析 Z-Score 工具』。
    3. ⚠️ 若需呼叫 CPI 或薪資工具，且使用者未指定時間，請務必直接代入系統當前時間 ({current_year}, {current_month}) 作為參數！
    4. 回答必須溫暖、專業，結尾記得帶「喵！」。
    
    「風格限制」：
    「【輸出風格】：請將數據融合成一段流暢、自然的綜合建議。絕對不要像機器人一樣重複相同的句型（例如一直重複『屬於平穩狀態』），請挑出漲跌幅最明顯的 1~2 項重點提醒即可。」
    """
    
    messages = [SystemMessage(content=full_sys_prompt)] + clean_messages
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

# ==========================================
# 3. 🕸️ 全域組裝 Graph
# ==========================================
graph_builder = StateGraph(State)
graph_builder.add_node("chatbot", chatbot_node)
graph_builder.add_node("tools", ToolNode(tools=tools)) 

graph_builder.add_edge(START, "chatbot")
graph_builder.add_conditional_edges("chatbot", tools_condition)
graph_builder.add_edge("tools", "chatbot")

memory = MemorySaver()
advisor_graph = graph_builder.compile(checkpointer=memory)

# 全域鎖
groq_semaphore = asyncio.Semaphore(5)

# ==========================================
# 4. 給外部 API (Router) 呼叫的進入點
# ==========================================
async def analyze_finance_advice(user_message: str, db: Session, current_user: Member) -> dict:
    try:
        await asyncio.wait_for(groq_semaphore.acquire(), timeout=3.0)
        try:
            # 🌟 透過 thread_id 告訴 LangGraph 這是哪個小主人的專屬記憶！
            result = await advisor_graph.ainvoke(
                {"messages": [("user", user_message)]},
                config={
                    "configurable": {
                        "db": db, 
                        "current_user": current_user,
                        "thread_id": str(current_user.user_id) # 🔑 記憶體的鑰匙
                    }
                }
            )
            # 🌟 把 AIMessage 整包拿出來
            ai_message = result["messages"][-1]
            
            # 🌟 挖出 Langchain 隱藏的 Token 收據
            usage_data = getattr(ai_message, "usage_metadata", {})
            converted_usage = {
                "prompt_tokens": usage_data.get("input_tokens", 0),
                "completion_tokens": usage_data.get("output_tokens", 0),
                "total_tokens": usage_data.get("total_tokens", 0)
            }
            
            # 🌟 改成回傳字典，把對話跟帳單一起送回去
            return {
                "content": ai_message.content,
                "usage": converted_usage
            }
        finally:
            groq_semaphore.release()
            
    except asyncio.TimeoutError:
        # 🌟 修正這裡：發生逾時，也必須回傳相同格式的字典，並且 Token 消耗為 0
        return {
            "content": "目前記帳喵喵太受歡迎啦！大腦運算正在排隊中，請小主人大約 1 分鐘後再試一次喵！",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        }
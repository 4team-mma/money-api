# web_app/services/advisor_graph_service.py
import json
import re

from typing import Annotated, Optional
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
from web_app.services.advisor_tools import FinancialAdvisorService
from web_app.prompts.ai_analysis_prompts import SYSTEM_INSTRUCTION
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
    def tool_get_salary_benchmark(
        year: str, 
        month: str, 
        industry: Optional[str]  | None=None ) -> str:
        """
        [重要提示給 LLM]：當使用者詢問「我的薪水算高嗎」、「我是不是薪水太低」、「跟同行比起來如何」時，或當使用者詢問薪資競爭力時呼叫，請呼叫此工具。
        參數說明：
        - year: 四碼年份字串
        - month: 兩碼月份字串
        - industry: (可選) 若使用者有明確提到他的行業 (例如: 資訊軟體業、教育業、製造業)，請填入此參數。
        """
        try:
            # 🛡️ 同理，加上神級防禦
            clean_year = re.sub(r'\D', '', str(year))
            clean_month = re.sub(r'\D', '', str(month)).zfill(2)

            result_dict = get_salary_comparison(
                year=clean_year, 
                month=clean_month, 
                industry=industry,
                db=db, 
                current_user=current_user
            )
            return json.dumps(result_dict, ensure_ascii=False)
        except Exception as e:
            return f"獲取薪資比較資料失敗：{str(e)}"

    
    # ------------------------------------------
    # 🌟 工具三：📊 進階分析 Z-Score 異常偵測 Tool
    # ------------------------------------------
    @tool
    async def tool_get_advanced_anomaly_analysis() -> str:
        """
        [進階診斷]：當使用者詢問「為什麼我最近存不到錢」、「我的消費正常嗎」或感覺「焦慮」時呼叫。
        此工具會透過 Z-Score 計算消費是否大幅偏離歷史常態，並識別『生活失衡』的訊號。
        """
        try:
            # 呼叫 FinancialAdvisorService 獲取 context
            context = await FinancialAdvisorService.get_ai_context(db, current_user)
            anomaly = context['metrics']['anomaly_analysis']
            
            # 建立結構化回傳，方便 AI 進行心理學轉譯
            report = {
                "is_anomaly": anomaly['is_anomaly'],
                "z_score": anomaly['z_score'],
                "severity": anomaly['severity'],
                "status_desc": "顯著異常" if anomaly['is_anomaly'] else "正常波動"
            }
            return json.dumps(report, ensure_ascii=False)
        except Exception as e:
            return f"異常偵測執行失敗：{str(e)}"

    # ------------------------------------------
    # 🌟 工具四：📈 全局財務視角整合 Tool
    # ------------------------------------------
    @tool
    async def tool_get_global_financial_overview() -> str:
        """
        [全局概覽]：當使用者詢問「我現在有多少錢」、「這個月支出多少」、「消費占比」或「整體分析」時呼叫。
        回傳包含：總支出、月增長率、當前淨資產、前三大消費類別。
        """
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
    # 🧠 初始化 LLM (大腦)
    # ------------------------------------------
    # 備用模型:
    # meta-llama/llama-4-scout-17b-16e-instruct
    # llama-3.3-70b-versatile
    llm = ChatGroq(model="meta-llama/llama-4-scout-17b-16e-instruct", temperature=0.2)
    llm_with_tools = llm.bind_tools(tools)

    # ------------------------------------------
    # 🤖 定義決策節點
    # ------------------------------------------
    def chatbot_node(state: State):
        # 🌟 1. 引入 datetime 獲取現在時間
        from datetime import datetime
        now = datetime.now()
        current_year = now.strftime("%Y")
        current_month = now.strftime("%m")

        # 🌟 2. 把時間與防呆指令塞進 Prompt 裡
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
        messages = [SystemMessage(content=full_sys_prompt)] + state["messages"]
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}
    # ------------------------------------------
    # 🕸️ 組裝 Graph (畫出流程圖)
    # ------------------------------------------
    # 組裝流程圖
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
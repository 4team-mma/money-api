import os
import pandas as pd
from io import BytesIO
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import extract, and_

# ReportLab 核心組件
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle

# ReportLab 繪圖組件
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.legends import Legend

# 專案內部引用
from ...dependencies import get_current_user
from ...database import get_db
from ...models import AddRecord, Member
from ...services.game_service import GameService

router = APIRouter()

# ==========================================
# 1. 輔助工具
# ==========================================
WEB_APP_ROOT = Path(__file__).resolve().parents[2]
FONT_NAME_IN_FILE = "NotoSansTC-Regular.ttf"
FONT_PATH = str(WEB_APP_ROOT / "assets" / "fonts" / FONT_NAME_IN_FILE)


def register_font():
    try:
        if not os.path.exists(FONT_PATH):
            return "Helvetica"
        pdfmetrics.registerFont(TTFont("MyFont", FONT_PATH))
        return "MyFont"
    except Exception:
        return "Helvetica"


def format_currency(value):
    """台幣整數不顯小數點"""
    val = float(value)
    if val == int(val):
        return f"{int(val):,}"
    return f"{val:,.2f}"


# ==========================================
# 2. PDF 組件
# ==========================================
def create_pie_chart(income, expense, font_name):
    d = Drawing(400, 180)
    # 使用 cast 避開 Pylance 對 slices 屬性的錯誤偵測
    pc = cast(Any, Pie()) 
    
    pc.x = 90
    pc.y = 20
    pc.width = 110
    pc.height = 110

    data = [max(float(income), 0), max(float(expense), 0)]
    if data[0] == 0 and data[1] == 0:
        data[0] = 0.1
    pc.data = data
    pc.labels = [f"${format_currency(income)}", f"${format_currency(expense)}"]

    # ✅ 必須先定義顏色變數，再賦值給 slices
    color_income = colors.HexColor("#2db6ec")  # 翡翠藍
    color_expense = colors.HexColor("#fb7185")  # 珊瑚粉
    
    pc.slices[0].fillColor = color_income
    pc.slices[1].fillColor = color_expense
    pc.slices.strokeWidth = 1
    pc.slices.strokeColor = colors.white
    
    leg = Legend()
    leg.x = 260
    leg.y = 120
    leg.fontName = font_name
    leg.fontSize = 11
    leg.colorNamePairs = [(color_income, "本期總收入"), (color_expense, "本期總支出")]
    d.add(pc)
    d.add(leg)
    return d


def generate_pdf_response(data, display_title, period_text, summary, user_nickname):
    output = BytesIO()
    font_name = register_font()
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=45,
        leftMargin=45,
        topMargin=40,
        bottomMargin=50,
    )
    elements = []

    title_style = ParagraphStyle(
        name="Title_CH", fontName=font_name, fontSize=26, alignment=1, spaceAfter=5
    )
    date_style = ParagraphStyle(
        name="Date_CH",
        fontName=font_name,
        fontSize=14,
        alignment=2,
        textColor=colors.HexColor("#ef4444"),
    )
    summary_style = ParagraphStyle(
        name="Summary_CH", fontName=font_name, fontSize=11, leading=14, spaceBefore=0
    )
    footer_style = ParagraphStyle(
        name="Footer_CH",
        fontName=font_name,
        fontSize=9,
        alignment=1,
        textColor=colors.grey,
        spaceBefore=40,
    )

    # A. 標題與動態日期
    elements.append(Paragraph(f"{user_nickname} 的 {display_title} 財務報表", title_style))
    elements.append(Paragraph(period_text, date_style))

    # B. 統計摘要
    elements.append(Spacer(1, 15))
    elements.append(Paragraph(f"<b>總計筆數：</b> {summary['count']} 筆", summary_style))
    elements.append(Paragraph(f"<b>本期淨額：</b> ${format_currency(summary['net'])}", summary_style))
    elements.append(Spacer(1, 15))

    # C. 圓餅圖
    elements.append(create_pie_chart(summary["income"], summary["expense"], font_name))
    elements.append(Spacer(1, 15))

    # D. 表格資料
    table_data = [["日期", "類型", "金額", "分類", "成員", "備註"]]
    for item in data:
        table_data.append([
            str(item["日期"]),
            item["類型"],
            format_currency(item["金額"]),
            item["分類"],
            item["成員"],
            item["備註"],
        ])

    t = Table(table_data, colWidths=[80, 50, 85, 80, 60, 150])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
    ]))
    elements.append(t)

    # E. 頁尾
    elements.append(Paragraph("—— MMA 團隊印製，提供您最專業的財務管理服務 ——", footer_style))

    doc.build(elements)
    output.seek(0)
    return output


# ==========================================
# 3. API 路由
# ==========================================
@router.get("/report", summary="🗂️ 匯出財務報表 (PDF/ csv / Excel)")
async def export_report(
    report_type: str = Query("monthly", description="報表類型：'monthly' 或 'annual'"),
    report_format: str = Query("excel", description="格式：'pdf', 'excel', 'csv'"),
    time_range: str = Query("current-month", description="時間區間代碼"),
    db: Session = Depends(get_db),
    current_user: Member = Depends(get_current_user),
):
    user_nickname = current_user.name or current_user.username
    now = datetime.now()
    filters = []
    period_text, display_title = "", ""

    # --- A. 時間計算核心邏輯 ---
    if time_range == "current-month":
        period_text, display_title = now.strftime("%Y年%m月"), "月度"
        filters = [
            extract("year", AddRecord.add_date) == now.year,
            extract("month", AddRecord.add_date) == now.month,
        ]
    elif time_range == "last-month":
        last_m = now.replace(day=1) - pd.Timedelta(days=1)
        period_text, display_title = last_m.strftime("%Y年%m月"), "月度"
        filters = [
            extract("year", AddRecord.add_date) == last_m.year,
            extract("month", AddRecord.add_date) == last_m.month,
        ]
    elif time_range.startswith("year-"):
        target_year = int(time_range.split("-")[1])
        period_text, display_title = f"{target_year}年度", "年度"
        filters = [extract("year", AddRecord.add_date) == target_year]
    elif "quarter" in time_range:
        current_q = (now.month - 1) // 3 + 1
        if time_range == "last-quarter":
            target_year = now.year if current_q > 1 else now.year - 1
            target_q = current_q - 1 if current_q > 1 else 4
        else:
            target_year, target_q = now.year, current_q
        period_text, display_title = f"{target_year}年第{target_q}季", "季度"
        start_m = (target_q - 1) * 3 + 1
        filters = [
            extract("year", AddRecord.add_date) == target_year,
            extract("month", AddRecord.add_date).between(start_m, start_m + 2),
        ]

    # --- B. 執行查詢 ---
    records = db.query(AddRecord).filter(and_(AddRecord.user_id == current_user.user_id, *filters)).all()
    if not records:
        raise HTTPException(status_code=404, detail="該時段內尚無帳務紀錄")

    summary = {
        "count": len(records),
        "income": sum(float(r.add_amount) for r in records if r.add_type),
        "expense": sum(float(r.add_amount) for r in records if not r.add_type),
    }
    summary["net"] = summary["income"] - summary["expense"]

    data_list = [
        {
            "日期": r.add_date,
            "類型": "收入" if r.add_type else "支出",
            "金額": float(r.add_amount),
            "分類": r.add_class,
            "成員": r.add_member,
            "備註": r.add_note or "-",
        }
        for r in records
    ]

    base_filename = f"{user_nickname}_{period_text}_{display_title}報表"
    encoded_filename = quote(base_filename)

    # 任務進度更新 (僅限 PDF 年度報表)
    if report_format == "pdf" and (report_type == "yearly" or "year-" in time_range):
        try:
            GameService.update_mission_progress(db, user_id=current_user.user_id, category='宏觀分析', increment=1)
            db.commit() 
        except Exception as e:
            db.rollback()
            print(f"任務更新失敗: {str(e)}")

    # --- C. 回傳格式判斷 ---
    if report_format == "pdf":
        pdf_content = generate_pdf_response(data_list, display_title, period_text, summary, user_nickname)
        return StreamingResponse(
            pdf_content,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}.pdf"}
        )

    # 資料表格式處理 (CSV/Excel)
    df = pd.DataFrame(data_list)
    df["金額"] = df["金額"].apply(format_currency)
    output = BytesIO()

    if report_format == "csv":
        # ✅ 使用 utf-8-sig (BOM) 解決 Excel 打開 CSV 中文亂碼問題
        csv_str = df.to_csv(index=False, encoding="utf-8-sig")
        output.write(csv_str.encode("utf-8-sig"))
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}.csv"}
        )
    else:
        # ✅ 預設輸出 Excel (.xlsx)
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False)
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}.xlsx"}
        )
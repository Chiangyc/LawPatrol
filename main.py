import os
import uvicorn
from typing import List, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# 風險分數：只用新的方案 B
from database import calculate_combined_risk

# Pydantic Schemas
from schemas import (
    CheckRequest,
    CheckResponse,
    ComplianceData,
    HighlightItem,
    HighlightDetails,
    FinalCase,
)

# ✨ 載入 async 版本邏輯
from logic import process_compliance_check_async

# 找出關鍵字在原文中的位置
from utils import find_text_indices


# 1. 載入環境變數 (讀取 .env)
load_dotenv()

# 2. 初始化 FastAPI
app = FastAPI(
    title="Ad Compliance Checker API",
    description="檢測食品與醫療廣告違規用語的後端 API",
    version="1.0.0",
)

# 3. 設定 CORS (跨來源資源共用)
origins = [
    "*",  # 目前先全部允許，之後上線可以鎖定網域
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    """檢查用，確認 Server 有活著"""
    return {"status": "running", "message": "Ad Compliance API is ready!"}


@app.post("/api/check_compliance", response_model=CheckResponse)
async def check_compliance(request: CheckRequest):
    """
    接收前端文字 -> 跑 LLM + 向量搜尋 -> 計算風險分數 -> 組成前端需要的回傳格式
    """
    user_text = request.selected_text

    if not user_text or not user_text.strip():
        raise HTTPException(status_code=400, detail="selected_text 不可為空")

    print(f"📩 收到檢測請求，User ID: {request.user_id}")
    print(f"📝 檢查文字片段: {user_text[:30]}...")

    # ---------- 1. 呼叫 AI 主流程 (用 async 版本) ----------
    try:
        logic_result: Dict[str, Any] = await process_compliance_check_async(user_text)
    except Exception as e:
        print(f"❌ 後端邏輯執行失敗: {e}")
        raise HTTPException(status_code=500, detail="Internal AI logic error")

    step1_output = logic_result.get("step1_output", {}) or {}
    vector_search_results = logic_result.get("vector_search_results", []) or []
    final_analysis = logic_result.get("final_analysis", {}) or {}

    # ---------- 2. 產業類別 ----------
    industry = step1_output.get("industry", "Unknown") or "Unknown"
    category = industry  # 先直接用 industry 當 category

    # ---------- 3. 風險分數 (方案 B：combined risk) ----------
    identified_tags = step1_output.get("identified_tags", []) or []
    tag_names = [item.get("tag") for item in identified_tags if item.get("tag")]

    risk = 0.0
    if tag_names:
        try:
            # calculate_combined_risk 會自己去 DB 查每個 tag 的歷史比例，
            # 再依照「這段文字實際踩到哪些 tag」組合出 0~1 之間的整體風險。
            risk = float(calculate_combined_risk(tag_names))
        except Exception as e:
            print(f"⚠️ 計算風險分數時發生錯誤: {e}")
            risk = 0.0
    else:
        risk = 0.0

    print(f"📊 本段文案風險分數 (0~1): {risk}")

    # ---------- 4. 把向量搜尋結果做成 tag -> cases 對照表 ----------
    tag_to_cases: Dict[str, List[Dict[str, Any]]] = {}
    for item in vector_search_results:
        tname = item.get("tag")
        if not tname:
            continue
        tag_to_cases[tname] = item.get("cases", []) or []

    # ---------- 5. 組成 highlights ----------
    analysis_results = final_analysis.get("analysis_results", []) or []
    highlights: List[HighlightItem] = []

    for analysis in analysis_results:
        trigger_word = analysis.get("trigger_word")
        tag = analysis.get("tag")
        reason = analysis.get("reason", "") or ""
        suggestion = analysis.get("suggestion", "") or ""
        reference_cases = analysis.get("reference_cases", []) or []

        if not trigger_word:
            continue

        # 5-1. 找這個字在原文的所有位置
        positions = find_text_indices(user_text, trigger_word)
        if not positions:
            positions = [{"start": -1, "end": -1}]

        # 5-2. 整理案例（把連結補上）
        cases_for_tag = tag_to_cases.get(tag, [])
        final_cases: List[FinalCase] = []

        for ref in reference_cases:
            ref_name = ref.get("product_name")
            ref_date = ref.get("date", "") or ""
            link = ""

            if ref_name:
                for c in cases_for_tag:
                    if c.get("product_name") == ref_name and (
                        not ref_date or c.get("date") == ref_date
                    ):
                        link = c.get("link", "") or ""
                        break

                final_cases.append(
                    FinalCase(
                        product_name=ref_name,
                        date=ref_date,
                        link=link,
                    )
                )

        details = HighlightDetails(
            reason=reason,
            suggestion=suggestion,
            cases=final_cases,
        )

        # 5-3. 每個出現位置都生一個 highlight item
        for pos in positions:
            highlights.append(
                HighlightItem(
                    trigger_words=trigger_word,
                    start_index=pos.get("start", -1),
                    end_index=pos.get("end", -1),
                    details=details,
                )
            )

    # ---------- 6. 組成最後回傳 ----------
    compliance_data = ComplianceData(
        category=category,
        risk=risk,
        highlights=highlights,
    )

    response = CheckResponse(
        status="success",
        data=compliance_data,
    )

    return response


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

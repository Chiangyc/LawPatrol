import uvicorn
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# 匯入我們剛剛寫好的資料格式
from schemas import CheckRequest, CheckResponse, ComplianceData, HighlightItem, HighlightDetails, FinalCase

# 1. 載入環境變數 (讀取 .env)
load_dotenv()

# 2. 初始化 FastAPI
app = FastAPI(
    title="Ad Compliance Checker API",
    description="檢測食品與醫療廣告違規用語的後端 API",
    version="1.0.0"
)

# 3. 設定 CORS (跨來源資源共用)
origins = [
    "*", 
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"], 
)

# --- API 路由區 ---

@app.get("/")
def read_root():
    """檢查用，確認 Server 有活著"""
    return {"status": "running", "message": "Ad Compliance API is ready!"}

@app.post("/api/check_compliance", response_model=CheckResponse)
async def check_compliance(request: CheckRequest):
    """
    主要功能：接收前端文字 -> 跑 AI 檢測 -> 回傳結果
    目前階段：回傳 Mock Data (假資料) 供前端測試 UI
    """
    print(f"收到請求 User ID: {request.user_id}")
    print(f"檢查文字片段: {request.selected_text[:20]}...") 

    # =========================================================
    # TODO: Day 3 合體區 
    # =========================================================

    # --- Day 1-2: Mock Data (假資料回傳) ---
    
    mock_response = CheckResponse(
        status="success",
        data=ComplianceData(
            category="Food",
            risk=0.8, # 80% 風險
            highlights=[
                HighlightItem(
                    trigger_words="甩油", # 【修正】這裡必須跟 schema 的 trigger_words 一致
                    start_index=12, 
                    end_index=14,
                    details=HighlightDetails(
                        reason="該詞彙暗示體重減輕或脂肪消除，屬於食品廣告中涉及『減肥』之違規詞句，違反食安法第28條。",
                        suggestion="建議改為『促進新陳代謝』或『調整體質』(需視具體成分而定)。",
                        cases=[
                            FinalCase(
                                product_name="XX綠茶",
                                date="2025-10",
                                link="https://www.fda.gov.tw/example_case_001"
                            )
                        ]
                    )
                ),
                HighlightItem(
                    trigger_words="改善糖尿病", # 【修正】這裡也改成 trigger_words
                    start_index=18,
                    end_index=23,
                    details=HighlightDetails(
                        reason="食品不得宣稱醫療效能，涉及疾病名稱屬嚴重違規。",
                        suggestion="請完全移除涉及疾病之詞彙，僅能敘述營養補給功能。",
                        cases=[
                            FinalCase(
                                product_name="XX膠囊",
                                date="2025-09",
                                link="https://www.fda.gov.tw/example_case_045"
                            )
                        ]
                    )
                )
            ]
        )
    )

    return mock_response

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
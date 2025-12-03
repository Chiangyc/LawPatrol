# 主程式 (API 路由)
# main.py
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
#這是 Chrome Extension 開發最重要的一步，沒設這個前端會完全連不上
origins = [
    "*", # 開發階段允許所有來源 (包含 localhost, 擴充功能 ID)
    # 上線後建議改為特定的 Extension ID，例如:
    # "chrome-extension://ajhifk...", 
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # 允許所有 HTTP 方法 (POST, GET...)
    allow_headers=["*"], # 允許所有 Header
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
    print(f"檢查文字片段: {request.selected_text[:20]}...") # 只印前20個字避免 Log 太長

    # =========================================================
    # TODO: Day 3 合體區 (未來要解開註解並替換假資料)
    # ---------------------------------------------------------
    # from logic import run_compliance_logic
    # real_result = run_compliance_logic(request.selected_text)
    # return real_result
    # =========================================================

    # --- Day 1-2: Mock Data (假資料回傳) ---
    # 這裡的結構必須嚴格遵守 schemas.py 定義的 CheckResponse
    
    mock_response = CheckResponse(
        status="success",
        data=ComplianceData(
            category="Food",
            overall_risk="High",
            highlights=[
                HighlightItem(
                    original_text="甩油",
                    start_index=12, # 假裝這是前端算出來的位置
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
                    original_text="改善糖尿病",
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

# 讓這個檔案可以直接用 python main.py 執行
if __name__ == "__main__":
    # reload=True 代表你改程式碼存檔後，Server 會自動重啟，開發很方便
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
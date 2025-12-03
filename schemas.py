# 定義 JSON 格式 (Pydantic)

# schemas.py
from pydantic import BaseModel, Field
from typing import List, Optional

# ==========================================
# 1. 前端 -> 後端 (Request)
# ==========================================
class CheckRequest(BaseModel):
    selected_text: str = Field(..., description="使用者在 Google Docs 選取的文字")
    user_id: Optional[str] = Field(None, description="使用者 ID，用於 Log")


# ==========================================
# 2. 內部邏輯用的模型 (給 Role B 寫邏輯參考用)
# ==========================================

# --- 第一次 LLM 回傳 (找違規詞) ---
class SuspectedItem(BaseModel):
    original_text: str   # 原文寫法，如 "甩油"
    standard_term: str   # 標準違規詞，如 "減肥"

class LLM1Response(BaseModel):
    category: str        # 產業類別 (Food, Cosmetic...)
    suspected_items: List[SuspectedItem]

# --- 向量資料庫查詢結果 (Vector DB) ---
class VectorCase(BaseModel):
    case_id: str
    date: str
    product_name: str
    standard_term: str
    explanation: str
    law: str
    similarity_score: float
    link: str

# --- 第二次 LLM 回傳 (產出建議) ---
class LLM2CaseRef(BaseModel):
    product_name: str
    date: str

class LLM2Analysis(BaseModel):
    original_text: str
    reason: str
    suggestion: str
    reference_cases: List[LLM2CaseRef] # LLM 挑選出的最相關案例摘要

class LLM2Response(BaseModel):
    analysis_results: List[LLM2Analysis]


# ==========================================
# 3. 後端 -> 前端 (Final Response)
# ==========================================

# 這是最後顯示在 Tooltip 裡的案例連結
class FinalCase(BaseModel):
    product_name: str
    date: str
    link: str # 這裡後端會把 Vector DB 的連結補進去

# 這是 Tooltip 裡的詳細內容
class HighlightDetails(BaseModel):
    reason: str
    suggestion: str
    cases: List[FinalCase]

# 這是每一個標記紅線的物件
class HighlightItem(BaseModel):
    original_text: str
    start_index: int
    end_index: int
    details: HighlightDetails

# 這是 data 層的結構
class ComplianceData(BaseModel):
    category: str
    overall_risk: str
    highlights: List[HighlightItem]

# 這是最外層的 API 回傳格式
class CheckResponse(BaseModel):
    status: str
    data: ComplianceData
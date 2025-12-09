from pydantic import BaseModel, Field
from typing import List, Optional, Union

# ==========================================
# 1. 前端 -> 後端 (Request)
# ==========================================
class CheckRequest(BaseModel):
    selected_text: str = Field(..., description="使用者在 Google Docs 選取的文字")
    user_id: Optional[str] = Field(None, description="使用者 ID，用於 Log")


# ==========================================
# 2. 內部邏輯用的模型 (給 Role B 寫邏輯參考用)
# ==========================================

# --- 第一次 LLM 回傳 (辨識 Tag 與觸發詞) ---
class IdentifiedTag(BaseModel):
    tag_name: str
    trigger_words: List[str]


class LLM1Response(BaseModel):
    category: str        # 產業 (Food, Cosmetic...)
    identified_tags: List[IdentifiedTag]

# --- 向量資料庫查詢結果 (Vector DB) ---
class VectorCase(BaseModel):
    case_id: str
    date: str
    product_name: str
    explanation: str
    law: str
    similarity_score: float
    link: str

class VectorTagGroup(BaseModel):
    tag_name: str
    cases: List[VectorCase] # 該 Tag 對應的 1-2 個案例

# --- 第二次 LLM 回傳 (產出建議) ---
class LLM2CaseRef(BaseModel):
    product_name: str
    date: str

class LLM2Analysis(BaseModel):
    trigger_word: str
    tag: str
    reason: str
    law: str
    reference_cases: List[LLM2CaseRef]

class LLM2Response(BaseModel):
    analysis_results: List[LLM2Analysis]
    suggestion: str



# ==========================================
# 3. 後端 -> 前端 (Final Response)
# ==========================================

class FinalCase(BaseModel):
    product_name: str
    date: str
    link: str
    explanation: str   # 新增：違規情節說明


class HighlightDetails(BaseModel):
    reason: str
    law: str                    # 新增：可能觸犯的法律
    cases: List[FinalCase]


class HighlightItem(BaseModel):
    tag_name: str          # 標籤名稱，例如「燃脂瘦身」
    tag_risk: float        # 單一 tag 的歷史風險 (0~1)
    trigger_words: str     # 對應前端的 original_text
    start_index: int
    end_index: int
    details: HighlightDetails


class ComplianceData(BaseModel):
    category: str
    risk: float  # 例如 0.8 (對應 80%)
    highlights: List[HighlightItem]
    suggestion: str        # 新增：整段文案的改寫建議


class CheckResponse(BaseModel):
    status: str
    data: ComplianceData

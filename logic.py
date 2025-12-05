import os
import json
import asyncio
from typing import List, Dict, Any, Optional

import google.generativeai as genai
from dotenv import load_dotenv

# 引入 Prompt
from prompts import STEP1_PROMPT_TEMPLATE, STEP3_PROMPT_TEMPLATE, get_formatted_tags_prompt

# 引入資料庫向量搜尋與 TAG_MAPPING
try:
    from database import search_vector_cases, TAG_MAPPING
except ImportError:
    print("⚠️ 警告: 無法引入 database.py，將使用 Mock DB 模式")
    search_vector_cases = None
    TAG_MAPPING: Dict[str, str] = {}

# 1. 載入環境變數
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")

# 2. 設定 Gemini
if api_key:
    genai.configure(api_key=api_key)
else:
    print("⚠️ 警告: 找不到 GOOGLE_API_KEY")

# 初始化模型 (使用 2.5 Flash 以求速度與準確平衡)
try:
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        generation_config={"response_mime_type": "application/json"}
    )
except Exception as e:
    model = None
    print(f"⚠️ 模型初始化失敗: {e}")

# ==========================================
# Step 1: 辨識標籤 (Async)
# ==========================================
async def identify_tags_async(text: str) -> Dict[str, Any]:
    """
    呼叫 Gemini：
    - 判斷產業 (industry)
    - 找出 identified_tags: [{ "tag": "...", "trigger_words": [...] }, ...]
    """
    if not model:
        return {"industry": "Unknown", "identified_tags": []}

    try:
        # 動態生成 Tag 分類說明字串 (要跟 TAG_MAPPING 一致)
        tags_context = get_formatted_tags_prompt()

        prompt = STEP1_PROMPT_TEMPLATE.format(
            tags_context_str=tags_context,
            user_text=text
        )

        response = await model.generate_content_async(prompt)
        return json.loads(response.text)
    except Exception as e:
        print(f"❌ Step 1 Error: {e}")
        return {"industry": "Unknown", "identified_tags": []}

# ==========================================
# Step 2: 向量搜尋 (Async Wrapper)
# ==========================================
async def search_db_async(user_text: str, tag: str, industry: Optional[str] = None):
    """
    包裝 Role A 的同步函式 search_vector_cases 變成 Async
    - 多帶一個 industry，讓向量搜尋可以限定產業
    - 若 database 尚未實作，則使用 Mock 資料
    """
    if search_vector_cases:
        # 呼叫真正的向量資料庫搜尋 (在 thread pool 執行，避免阻塞 event loop)
        return await asyncio.to_thread(search_vector_cases, user_text, tag, industry)
    else:
        # Mock 模式 (database.py 尚未完成時用來測試流程)
        await asyncio.sleep(0.1)
        print(f"⚠️ [Mock DB] Searching for tag={tag}, industry={industry} ...")
        return [{
            "case_id": "MOCK",
            "product_name": "模擬案例",
            "explanation": "這是因為 database.py 尚未更新所顯示的假資料。",
            "law": "食安法",
            "date": "2025-01",
            "link": "#",
            "similarity_score": 0.5,
        }]

# ==========================================
# Step 3: 生成建議 (Async)
# ==========================================
async def generate_analysis_async(
    user_text: str,
    step1_result: Dict[str, Any],
    vector_results: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    呼叫第二次 Gemini：
    - Input: 原始文案 + Step1 判斷 + 向量查詢結果
    - Output: analysis_results（每個違規字的原因＋建議＋參考案例）
    """
    if not model:
        return {"analysis_results": []}

    try:
        vector_results_str = json.dumps(vector_results, ensure_ascii=False)
        step1_result_str = json.dumps(step1_result, ensure_ascii=False)

        prompt = STEP3_PROMPT_TEMPLATE.format(
            user_text=user_text,
            step1_result=step1_result_str,
            vector_results=vector_results_str
        )

        response = await model.generate_content_async(prompt)
        return json.loads(response.text)
    except Exception as e:
        print(f"❌ Step 3 Error: {e}")
        return {"analysis_results": []}

# ==========================================
# Main Logic Orchestrator (給 Role A 呼叫的入口)
# ==========================================
def process_compliance_check(user_text: str) -> Dict[str, Any]:
    """
    同步入口函式：
    - 給 main.py / FastAPI 使用
    - 內部實際用 asyncio 跑非同步邏輯
    """
    return asyncio.run(process_compliance_check_async(user_text))


async def process_compliance_check_async(user_text: str) -> Dict[str, Any]:
    print(f"\n🚀 [AI Logic] 開始分析: {user_text[:20]}...")

    # 1. Step 1: 找產業 + Tag + Trigger Words
    step1_output = await identify_tags_async(user_text)

    # --- 安全閥：過濾掉「不在 TAG_MAPPING 裡的標籤」 ---
    raw_tags = step1_output.get("identified_tags", [])
    valid_tag_names = set(TAG_MAPPING.keys())
    clean_tags = []
    dropped_tags = []

    for item in raw_tags:
        tname = item.get("tag")
        if tname in valid_tag_names:
            clean_tags.append(item)
        else:
            dropped_tags.append(tname)

    if dropped_tags:
        print(f"ℹ️ [AI Logic] 已過濾掉未知標籤: {dropped_tags}")

    step1_output["identified_tags"] = clean_tags

    # 取得產業（Food / Cosmetic / Medicine / Device / Unknown）
    industry = step1_output.get("industry")

    # 2. Step 2: 平行查詢資料庫（向量搜尋）
    tasks = []
    tags_found = step1_output.get("identified_tags", [])

    for item in tags_found:
        tag = item.get("tag")
        if not tag:
            continue
        # 建立查詢任務，帶入 industry
        tasks.append(search_db_async(user_text, tag, industry))

    if tasks:
        db_results_list = await asyncio.gather(*tasks)
    else:
        db_results_list = []

    # 整理結果格式：[
    #   {"tag": "燃脂瘦身", "cases": [...]},
    #   {"tag": "治療", "cases": [...]},
    # ]
    vector_search_results: List[Dict[str, Any]] = []
    for i, item in enumerate(tags_found):
        tag_name = item.get("tag")
        cases_for_tag = db_results_list[i] if i < len(db_results_list) else []
        vector_search_results.append({
            "tag": tag_name,
            "cases": cases_for_tag
        })

    # 3. Step 3: 綜合分析（產生違規原因 + 建議）
    if not vector_search_results:
        final_analysis = {"analysis_results": []}
    else:
        final_analysis = await generate_analysis_async(
            user_text=user_text,
            step1_result=step1_output,
            vector_results=vector_search_results
        )

    print("✅ [AI Logic] 分析完成")

    return {
        "step1_output": step1_output,
        "vector_search_results": vector_search_results,
        "final_analysis": final_analysis
    }


# --- 測試區塊 ---
if __name__ == "__main__":
    test_text = "本產品採用獨家奈米技術，保證三天甩油，並能改善糖尿病體質。"
    result = process_compliance_check(test_text)
    print(json.dumps(result, indent=2, ensure_ascii=False))

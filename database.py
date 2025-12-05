# database.py
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from typing import List

# --- New: Pinecone + Gemini ---
import google.generativeai as genai
from pinecone import Pinecone

# ======================================================
# 0. 載入環境變數
# ======================================================
load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PORT = os.getenv("DB_PORT", "5432")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "ad-compliance")

# ======================================================
# 1. Tag 對照表（中文 → SQL 欄位名稱）
# ======================================================
TAG_MAPPING = {
    # --- 提及醫療與治療行為 ---
    "治療": "tag_treatment",
    "症狀緩解": "tag_symptom_relief",
    "預防": "tag_prevention",
    "痊癒": "tag_cure",
    "消腫": "tag_swelling",
    "矯正復健": "tag_rehabilitation",
    "療法": "tag_therapy",
    "傷口護理": "tag_wound_care",

    # --- 宣稱生理機能改變 ---
    "再生抗老": "tag_anti_aging",
    "增生": "tag_proliferation",
    "活化機能": "tag_activation",
    "燃脂瘦身": "tag_slimming",
    "排毒解酒": "tag_detox",
    "拉提緊緻": "tag_lifting",
    "生髮育髮": "tag_hair_growth",
    "豐胸": "tag_breast_enhancement",
    "長高發育": "tag_growth",
    "生殖機能": "tag_reproductive",
    "睡眠情緒": "tag_sleep_mood",
    "免疫體質": "tag_immunity",

    # --- 語氣過度誇大與絕對 ---
    "唯一第一": "tag_top_rank",
    "完全永久": "tag_permanent",
    "奇蹟神效": "tag_miracle",
    "保證承諾": "tag_guarantee",
    "立即速效": "tag_immediate_effect",

    # --- 提及權威與高風險疾病 ---
    "臨床實驗": "tag_clinical_trial",
    "醫師專家": "tag_expert",
    "見證推薦": "tag_testimonial",
    "癌症": "tag_cancer",
    "三高心血管": "tag_cardiovascular",
    "發炎": "tag_inflammation",
}

# ======================================================
# 2. 初始化 Gemini（Embedding）與 Pinecone
# ======================================================
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
else:
    print("⚠️ WARNING: GOOGLE_API_KEY 未設定，無法產生向量")

pc = None
index = None
if PINECONE_API_KEY:
    try:
        pc = Pinecone(api_key=PINECONE_API_KEY)
        index = pc.Index(PINECONE_INDEX_NAME)
    except Exception as e:
        print(f"⚠️ 初始化 Pinecone 失敗：{e}")
else:
    print("⚠️ WARNING: PINECONE_API_KEY 未設定，無法進行向量搜尋")


# ======================================================
# 3. Postgres 連線
# ======================================================
def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT,
            sslmode="require"  # Supabase 必須加
        )
        return conn
    except Exception as e:
        print(f"❌ 資料庫連線失敗: {e}")
        return None


# ======================================================
# 4. 風險查詢
# ======================================================
def get_risk_info(tag_name: str) -> float:
    sql_column = TAG_MAPPING.get(tag_name)
    if not sql_column:
        return 0.0

    conn = get_db_connection()
    if not conn:
        return 0.5  # fallback

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM public.violation_cases;")
            total = cursor.fetchone()[0]

            if total == 0:
                return 0.0

            cursor.execute(f"SELECT COUNT(*) FROM public.violation_cases WHERE {sql_column} = 1;")
            cnt = cursor.fetchone()[0]

            return round(cnt / total, 3)

    except Exception as e:
        print(f"❌ risk SQL 錯誤: {e}")
        return 0.0
    finally:
        conn.close()


def calculate_max_risk(tags: List[str]) -> float:
    if not tags:
        return 0.0
    return max(get_risk_info(tag) for tag in tags)


# ======================================================
# 5. 向量查詢
# ======================================================
def embed_text(text: str):
    if not GOOGLE_API_KEY:
        return None

    try:
        resp = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="retrieval_query",
        )
        return resp["embedding"]
    except Exception as e:
        print(f"❌ 產生 embedding 失敗: {e}")
        return None


def search_vector_cases(user_text: str, tag: str, industry: str | None = None, top_k: int = 2):
    """
    產出：
    [
        {
            "case_id": "123",
            "product_name": "...",
            "explanation": "...",
            "law": "...",
            "date": "2023-01",
            "link": "https://...",
            "similarity_score": 0.87
        }
    ]
    """
    if index is None:
        print("⚠️ Pinecone 尚未初始化")
        return []

    embedding = embed_text(user_text)
    if embedding is None:
        return []

    # 準備 filter：至少要 tag 符合
    filter_dict = {
        "tag_name": {"$in": [tag]}
    }
    # 若有傳入 industry，就一併限制（Food, Cosmetic, Medicine, Device）
    if industry:
        filter_dict["industry"] = industry

    try:
        result = index.query(
            vector=embedding,
            top_k=top_k,
            include_metadata=True,
            filter=filter_dict,
        )
    except Exception as e:
        print(f"❌ Pinecone 查詢錯誤: {e}")
        return []

    matches = result.get("matches", []) or []
    output = []

    for m in matches:
        meta = m.get("metadata", {}) or {}
        output.append({
            "case_id": m.get("id"),
            "product_name": meta.get("product_name", ""),
            "explanation": meta.get("explanation", ""),
            "law": meta.get("law", ""),
            "date": meta.get("date", ""),
            "link": meta.get("link", ""),
            "similarity_score": m.get("score", 0.0),
        })

    return output



# ======================================================
# 6. 測試區（直接 python database.py）
# ======================================================
if __name__ == "__main__":
    print("🔥 測試 search_vector_cases()")

    text = "本產品有效改善發炎問題，快速舒緩不適。"

    res = search_vector_cases(text, tag="治療", top_k=2)

    print(res)

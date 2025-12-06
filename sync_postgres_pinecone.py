# sync_postgres_pinecone.py

import os
import time
import psycopg2
from psycopg2.extras import RealDictCursor
from pinecone import Pinecone
import google.generativeai as genai
from dotenv import load_dotenv

# 1. 載入環境變數
load_dotenv()

# 2. 設定 API
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index_name = os.getenv("PINECONE_INDEX_NAME", "ad-compliance")
index = pc.Index(index_name)

# ==========================================
# 設定：SQL 欄位轉 Tag 名稱的對照邏輯
# （跟 database.py 的 TAG_MAPPING 反向對應）
# ==========================================
SQL_TO_TAG_MAP = {
    # --- 提及醫療與治療行為 ---
    "tag_treatment": ["治療"],
    "tag_symptom_relief": ["症狀緩解"],
    "tag_prevention": ["預防"],
    "tag_cure": ["痊癒"],
    "tag_swelling": ["消腫"],
    "tag_rehabilitation": ["矯正復健"],
    "tag_therapy": ["療法"],
    "tag_wound_care": ["傷口護理"],

    # --- 宣稱生理機能改變 ---
    "tag_anti_aging": ["再生抗老"],
    "tag_proliferation": ["增生"],
    "tag_activation": ["活化機能"],
    "tag_slimming": ["燃脂瘦身"],
    "tag_detox": ["排毒解酒"],
    "tag_lifting": ["拉提緊緻"],
    "tag_hair_growth": ["生髮育髮"],
    "tag_breast_enhancement": ["豐胸"],
    "tag_growth": ["長高發育"],
    "tag_reproductive": ["生殖機能"],
    "tag_sleep_mood": ["睡眠情緒"],
    "tag_immunity": ["免疫體質"],

    # --- 語氣過度誇大與絕對 ---
    "tag_top_rank": ["唯一第一"],
    "tag_permanent": ["完全永久"],
    "tag_miracle": ["奇蹟神效"],
    "tag_guarantee": ["保證承諾"],
    "tag_immediate_effect": ["立即速效"],

    # --- 提及權威與高風險疾病 ---
    "tag_clinical_trial": ["臨床實驗"],
    "tag_expert": ["醫師專家"],
    "tag_testimonial": ["見證推薦"],
    "tag_cancer": ["癌症"],
    "tag_cardiovascular": ["三高心血管"],
    "tag_inflammation": ["發炎"],
}

# ==========================================
# 1. 取得 PostgreSQL 連線
# ==========================================
# sync_postgres_pinecone.py (只貼出需要改的部分)

def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            database=os.getenv("DB_NAME", "ad_compliance_db"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "password"),
            port=os.getenv("DB_PORT", "5432"),
            options='-c statement_timeout=0'  # ⭐ 直接在連線時關掉 timeout
        )

        # 如果你比較安心，也可以再多跑一次保險：
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout TO 0;")

        return conn

    except Exception as e:
        print(f"❌ DB 連線失敗: {e}")
        return None


# ==========================================
# 2. 核心同步邏輯：只上傳「有 Tag」的案例
# ==========================================
def sync_data():
    conn = get_db_connection()
    if not conn:
        return

    print("🚀 開始從 PostgreSQL 同步資料到 Pinecone...")

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:

            # 1️⃣ 準備 Tag 欄位 SQL & WHERE 條件
            tag_columns_sql = ", ".join(SQL_TO_TAG_MAP.keys())
            where_clause = " OR ".join([f"{col} = 1" for col in SQL_TO_TAG_MAP.keys()])

            # 2️⃣ 查詢：只抓「有任一個 tag = 1」的案例，並加上 LIMIT
            query = f"""
                SELECT id,
                       product_name,
                       case_explaination AS case_explanation,
                       violation_law,
                       case_date,
                       source_link,
                       industry,
                       violation_type,
                       {tag_columns_sql}
                FROM public.violation_cases
                WHERE {where_clause}
                ORDER BY id
                LIMIT 242;   -- 🔧 想同步更多就改這裡
            """

            print("\n🔍 即將執行 SQL：")
            print(query)

            cursor.execute(query)
            rows = cursor.fetchall()

            print(f"\n📊 共找到 {len(rows)} 筆「有 Tag 的資料」，開始處理...\n")

            # 3️⃣ 批次上傳到 Pinecone
            batch_vectors = []
            batch_size = 50

            for i, row in enumerate(rows):
                case_id = str(row["id"])
                text_to_embed = row["case_explanation"]

                if not text_to_embed or not text_to_embed.strip():
                    print(f"⚠️ 跳過 ID {case_id}（說明為空）")
                    continue

                # 4️⃣ 整理 tags_list：把 =1 的欄位轉成中文 Tag
                tags_list = []

                for col, tag_names in SQL_TO_TAG_MAP.items():
                    if row.get(col) == 1:
                        tags_list.extend(tag_names)

                # 保留原本 violation_type 作為補充 Tag
                if row.get("violation_type"):
                    tags_list.append(row["violation_type"])

                # 去重
                tags_list = list(set(tags_list))

                # 5️⃣ 文字 → 向量（Gemini embedding）
                try:
                    embedding_resp = genai.embed_content(
                        model="models/text-embedding-004",
                        content=text_to_embed,
                        task_type="retrieval_document"
                    )
                    vector = embedding_resp["embedding"]
                except Exception as e:
                    print(f"❌ ID {case_id} 向量化失敗：{e}")
                    continue

                # 6️⃣ metadata 準備進 Pinecone
                metadata = {
                    "product_name": row.get("product_name") or "未知產品",
                    "explanation": text_to_embed,
                    "law": row.get("violation_law") or "",
                    "date": str(row.get("case_date") or ""),
                    "link": row.get("source_link") or "",
                    "industry": row.get("industry") or "Food",
                    "tag_name": tags_list,
                }

                batch_vectors.append((case_id, vector, metadata))

                print(f"✅ 已處理 {i+1}/{len(rows)} → {metadata['product_name']} | tags={tags_list}")

                # 每 50 筆上傳一次
                if len(batch_vectors) >= batch_size:
                    index.upsert(vectors=batch_vectors)
                    print(f"📤 上傳 {len(batch_vectors)} 筆到 Pinecone")
                    batch_vectors = []
                    time.sleep(1)

            # 上傳剩下的
            if batch_vectors:
                index.upsert(vectors=batch_vectors)
                print(f"📤 最後上傳 {len(batch_vectors)} 筆")

    except Exception as e:
        print(f"❌ 同步過程錯誤：{e}")
    finally:
        conn.close()
        print("\n🏁 Pinecone 同步作業完成")

if __name__ == "__main__":
    sync_data()

# auto_tag_cases.py

import os
import time
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

import google.generativeai as genai

from prompts import TAG_CATEGORIES, get_formatted_tags_prompt, STEP1_PROMPT_TEMPLATE
from database import TAG_MAPPING  # 直接沿用你原本的 Tag 對照表

# ========= 1. 環境變數 & 模型設定 =========

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
DB_PORT = os.getenv("DB_PORT", "5432")

API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    raise RuntimeError("❌ 找不到 GOOGLE_API_KEY，請先在 .env 設定")

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    generation_config={"response_mime_type": "application/json"}
)

# 一次處理幾筆（可以自行調整）
BATCH_SIZE = 50
# 最多處理幾筆（你說 536 筆）
MAX_TOTAL = 536


# ========= 2. DB 連線 =========

def get_conn():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT
    )


# ========= 3. 組 SQL 條件：找「尚未標 Tag」的資料 =========

TAG_COLUMNS = list(TAG_MAPPING.values())
# e.g. ["tag_treatment", "tag_symptom_relief", ..., "tag_inflammation"]

def build_unlabeled_where_clause() -> str:
    """
    找出「所有 Tag 欄位都是 0」的資料。
    """
    parts = []
    for col in TAG_COLUMNS:
        parts.append(f"{col} = 0")
    return " AND ".join(parts)


UNLABELED_WHERE = build_unlabeled_where_clause()


# ========= 4. 呼叫 LLM 做 Step1：辨識 Tag =========
# （industry 有沒有都無所謂，我們只用 identified_tags）

def call_step1_llm(text: str):
    tags_context = get_formatted_tags_prompt()
    prompt = STEP1_PROMPT_TEMPLATE.format(
        tags_context_str=tags_context,
        user_text=text
    )
    resp = model.generate_content(prompt)
    try:
        data = resp.json  # 新版 SDK，有可能存在
    except Exception:
        import json
        data = json.loads(resp.text)
    return data


# ========= 5. 把 LLM 的結果轉成「只更新 Tag 欄位」 =========

def build_tag_update_fields(step1_result):
    """
    step1_result 範例：
    {
      "industry": "Food",   # ⚠️ 這個現在會被忽略
      "identified_tags": [
        { "tag": "保證承諾", "trigger_words": ["保證"] },
        { "tag": "燃脂瘦身", "trigger_words": ["甩油"] }
      ]
    }

    回傳：
    { "tag_guarantee": 1, "tag_slimming": 1 }
    """
    identified = step1_result.get("identified_tags", []) or []

    update_map = {}

    for item in identified:
        tag_name = item.get("tag")
        if not tag_name:
            continue

        col = TAG_MAPPING.get(tag_name)
        if not col:
            # 不在定義裡的 Tag 先忽略
            continue

        update_map[col] = 1  # 只記「有 / 沒有」

    return update_map


# ========= 6. 主流程：批次撈資料 -> LLM 標 Tag -> 回寫 =========

def auto_tag_loop():
    print("🚀 auto_tag_cases 啟動（只更新 Tag，不修改 industry）")

    conn = get_conn()
    conn.autocommit = False  # 用 transaction 批次 commit

    processed_total = 0  # ⭐ 已處理總筆數

    try:
        while True:
            # ⭐ 如果已經處理到上限，就結束
            if processed_total >= MAX_TOTAL:
                print(f"✅ 已處理 {processed_total} 筆，達到上限 {MAX_TOTAL}，任務結束")
                break

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                print("🔍 準備撈一批尚未標 Tag 的資料...")

                # 計算這一批最多還能撈幾筆（避免超過 536）
                remaining = MAX_TOTAL - processed_total
                limit = min(BATCH_SIZE, remaining)

                sql = f"""
                    SELECT id, product_name, case_explaination
                    FROM violation_cases
                    WHERE {UNLABELED_WHERE}
                    ORDER BY id
                    LIMIT {limit};
                """
                cur.execute(sql)
                rows = cur.fetchall()

            if not rows:
                print("✅ 找不到更多未標註的案件，任務結束")
                break

            print(f"📦 本批次共有 {len(rows)} 筆，開始呼叫 LLM 標 Tag...")

            for row in rows:
                case_id = row["id"]
                product_name = row.get("product_name") or ""
                text = row.get("case_explaination") or ""

                if not text.strip():
                    print(f"⚠️ ID {case_id} 案情說明為空，略過")
                    continue

                print(f"\n📝 [ID {case_id}] {product_name[:20]} ...")

                # --- Step1: LLM 辨識 Tag ---
                try:
                    step1 = call_step1_llm(text)
                except Exception as e:
                    print(f"❌ LLM 呼叫失敗，略過此筆: {e}")
                    continue

                update_fields = build_tag_update_fields(step1)

                if not update_fields:
                    print("ℹ️ 沒有偵測到任何符合定義的 Tag，略過更新")
                    continue

                # --- 組 UPDATE SQL（只更新 tag 欄位） ---
                set_clauses = []
                params = []

                for col, val in update_fields.items():
                    set_clauses.append(f"{col} = %s")
                    params.append(val)

                params.append(case_id)

                update_sql = f"""
                    UPDATE violation_cases
                    SET {", ".join(set_clauses)}
                    WHERE id = %s;
                """

                with conn.cursor() as cur2:
                    cur2.execute(update_sql, params)

                print(f"✅ 已更新 ID {case_id} 的 Tag 欄位：{list(update_fields.keys())}")
                processed_total += 1  # ⭐ 累計總共處理幾筆

                # 避免打太快被 API 限速，可依情況調整或拿掉
                time.sleep(0.2)

            # 每一批 commit 一次
            conn.commit()
            print("💾 本批次已寫入資料庫並 commit\n")

    except Exception as e:
        conn.rollback()
        print(f"❌ 發生錯誤，已 rollback：{e}")
    finally:
        conn.close()
        print("🏁 auto_tag_cases 結束")


if __name__ == "__main__":
    auto_tag_loop()

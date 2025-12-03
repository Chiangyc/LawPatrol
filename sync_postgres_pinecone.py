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
# ==========================================
# 這是根據你的 database.py 反轉過來的對應表
# Key: SQL 欄位名稱 (必須存在於資料庫中)
# Value: 要存入 Pinecone 的中文 Tag 列表
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
def get_db_connection():
    try:
        return psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            database=os.getenv("DB_NAME", "ad_compliance_db"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "password"),
            port=os.getenv("DB_PORT", "5432")
        )
    except Exception as e:
        print(f"❌ DB 連線失敗: {e}")
        return None

# ==========================================
# 2. 核心同步邏輯
# ==========================================
def sync_data():
    conn = get_db_connection()
    if not conn:
        return

    print("🚀 開始從 PostgreSQL 同步資料到 Pinecone...")
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # A. 撈取所有案例 (只撈需要欄位)
            
            # 動態生成查詢欄位：自動把 SQL_TO_TAG_MAP 裡的所有 key 加入查詢
            # 這樣以後增加欄位只要改上面的 Map，不用改這裡的 SQL
            tag_columns_sql = ", ".join(SQL_TO_TAG_MAP.keys())
            
            query = f"""
                SELECT id, product_name, case_explanation, violated_law, 
                       case_date, source_link, industry, violation_type,
                       {tag_columns_sql}
                FROM cases;
            """
            
            # 注意：如果資料庫還沒有建立這些欄位，這裡會報錯。
            # 請確保 DB Schema 已經更新。
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            print(f"📊 總共發現 {len(rows)} 筆案例，準備處理...")
            
            batch_vectors = []
            batch_size = 50 # 每 50 筆上傳一次，避免網路卡住
            
            for i, row in enumerate(rows):
                case_id = str(row['id'])
                text_to_embed = row['case_explanation']
                
                # 防呆：如果說明是空的，跳過
                if not text_to_embed or len(text_to_embed.strip()) == 0:
                    print(f"⚠️ 跳過 ID {case_id}: 案情說明為空")
                    continue

                # B. 處理 Tags (將 SQL 欄位轉為 List)
                # Pinecone 支援 list 篩選，例如 filter={"tag_name": "治療"} 
                # 若 metadata["tag_name"] 是 ["治療", "預防"]，該篩選會命中。
                tags_list = []
                
                # 1. 處理 0/1 開關欄位
                for col, tag_names in SQL_TO_TAG_MAP.items():
                    # 檢查 row 裡面有沒有這個欄位 (因為動態生成，一定有)，且值為 1
                    if row.get(col) == 1:
                        tags_list.extend(tag_names)
                
                # 2. 處理文字型欄位 (violation_type) - 保留原本邏輯作為補充
                if row.get('violation_type'):
                    tags_list.append(row['violation_type'])
                
                # 去除重複 Tag
                tags_list = list(set(tags_list))

                # C. 呼叫 Gemini 轉向量 (768維)
                try:
                    embedding_resp = genai.embed_content(
                        model="models/text-embedding-004",
                        content=text_to_embed,
                        task_type="retrieval_document"
                    )
                    vector = embedding_resp['embedding']
                except Exception as e:
                    print(f"⚠️ ID {case_id} 向量化失敗: {e}")
                    continue

                # D. 準備 Metadata (要存進 Pinecone 的資料)
                metadata = {
                    "product_name": row['product_name'] or "未知產品",
                    "explanation": text_to_embed,
                    "law": row['violated_law'] or "",
                    "date": str(row['case_date']) if row['case_date'] else "",
                    "link": row['source_link'] or "",
                    "industry": row['industry'] or "Food",
                    "tag_name": tags_list  # 關鍵：存成 List 讓 logic.py 可以篩選
                }

                # 加入批次列表
                batch_vectors.append((case_id, vector, metadata))
                
                print(f"✅ 處理進度: {i+1}/{len(rows)} - {row['product_name']}")

                # E. 批次上傳
                if len(batch_vectors) >= batch_size:
                    index.upsert(vectors=batch_vectors)
                    print(f"📤 已上傳 {len(batch_vectors)} 筆資料到 Pinecone")
                    batch_vectors = [] # 清空
                    time.sleep(1) # 休息一下避免 API Rate Limit

            # 處理剩下的
            if batch_vectors:
                index.upsert(vectors=batch_vectors)
                print(f"📤 已上傳最後 {len(batch_vectors)} 筆資料")

    except Exception as e:
        print(f"❌ 同步過程發生錯誤: {e}")
        print("💡 提示：請檢查 PostgreSQL 中是否已經建立了所有 TAG_MAPPING 中定義的欄位。")
    finally:
        conn.close()
        print("🏁 同步作業結束")

if __name__ == "__main__":
    sync_data()
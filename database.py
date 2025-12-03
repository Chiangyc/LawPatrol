import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from typing import List

load_dotenv()

# ==========================================
# 1. Tag 對照表 (AI 中文 -> SQL 英文欄位)
# ==========================================
# 根據你的 SQL Schema 截圖設定
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

# ==========================================
# 2. 資料庫連線設定
# ==========================================
def get_db_connection():
    """建立 PostgreSQL 資料庫連線"""
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            database=os.getenv("DB_NAME", "ad_compliance_db"), # 修改為你們的 DB 名稱
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "password"),
            port=os.getenv("DB_PORT", "5432")
        )
        return conn
    except Exception as e:
        print(f"❌ 資料庫連線失敗: {e}")
        return None

# ==========================================
# 3. 核心功能：查詢風險等級
# ==========================================
def get_risk_info(tag_name: str) -> float:
    """
    輸入: '治療'
    輸出: 風險值 0.0 ~ 1.0 (例如 0.85 代表 85%)
    """
    
    # A. 找出對應的 SQL 欄位
    sql_column = TAG_MAPPING.get(tag_name)
    
    # 如果 AI 找出的 Tag 不在我們的資料庫欄位定義中，回傳 0.0 (代表無特別風險數據)
    if not sql_column:
        # print(f"⚠️ 未知的 Tag: {tag_name}，回傳預設風險 0.0")
        return 0.0

    conn = get_db_connection()
    
    # --- 防呆機制：如果資料庫沒連上，回傳假資料 (讓前端不會壞掉) ---
    if not conn:
        # 這裡模擬四分位數邏輯：某些詞預設就是高風險
        if tag_name in ["治療", "減肥瘦身", "醫療效能", "癌症", "Tag_治療"]:
            return 0.8
        return 0.5
    
    # -------------------------------------------------------

    try:
        with conn.cursor() as cursor:
            # B. 執行 SQL 查詢
            # 邏輯：計算該 Tag 為 1 的案例數 / 總案例數
            
            # 1. 算出總案例數
            cursor.execute("SELECT COUNT(*) FROM cases;")
            total_count = cursor.fetchone()[0]
            
            if total_count == 0:
                return 0.0

            # 2. 算出該 Tag 出現次數
            query = f"SELECT COUNT(*) FROM cases WHERE {sql_column} = 1;"
            cursor.execute(query)
            tag_count = cursor.fetchone()[0]
            
            # 3. 計算百分比 (0.0 ~ 1.0)
            percentage = (tag_count / total_count) 
            
            return float(percentage)

    except Exception as e:
        print(f"❌ SQL 查詢錯誤: {e}")
        return 0.0
    finally:
        if conn:
            conn.close()

def calculate_max_risk(tags: List[str]) -> float:
    """
    輸入: ['治療', '預防', '未知標籤']
    輸出: 列表中風險最高的數值 (例如 0.8)
    """
    if not tags:
        return 0.0
        
    max_risk = 0.0
    
    for tag in tags:
        risk = get_risk_info(tag)
        if risk > max_risk:
            max_risk = risk
            
    return max_risk

# ==========================================
# 4. 測試區 (直接執行 python database.py)
# ==========================================
if __name__ == "__main__":
    # 測試連線
    print("--- 測試資料庫連線 ---")
    conn = get_db_connection()
    if conn:
        print("✅ 連線成功！")
        conn.close()
    else:
        print("⚠️ 連線失敗 (這是預期的，如果你還沒架好 PostgreSQL)")

    # 測試邏輯
    print("\n--- 測試風險查詢 ---")
    print(f"Tag '治療' 的風險: {get_risk_info('治療')}")
    
    test_tags = ["治療", "預防", "未知標籤"]
    print(f"Tags {test_tags} 的最高風險: {calculate_max_risk(test_tags)}")
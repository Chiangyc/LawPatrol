import os
import time
from pinecone import Pinecone, ServerlessSpec
import google.generativeai as genai
from dotenv import load_dotenv

# 1. 載入 .env 裡的 API Key
load_dotenv()

# 2. 設定 API
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
index_name = os.environ.get("PINECONE_INDEX_NAME", "ad-compliance")
index = pc.Index(index_name)

# 3. 準備測試資料 (這裡模擬從 PostgreSQL 撈出來的資料)
# 根據你們的 Tag 邏輯，我們準備兩類案例：減肥瘦身、醫療效能
mock_cases = [
    {
        "id": "case_001",
        "text": "XX綠茶宣稱可以消除腹部脂肪，輕鬆甩油，回復窈窕身材。",
        "metadata": {
            "product_name": "XX綠茶",
            "date": "2024-01-15",
            "law": "食安法第28條",
            "industry": "Food",
            "tag_name": "減肥瘦身", # 對應 Tag
            "link": "https://example.com/case/001",
            "explanation": "宣稱可消除腹部脂肪，涉及誇張或易生誤解。"
        }
    },
    {
        "id": "case_002",
        "text": "XX膠囊廣告內容提及改善糖尿病體質，調節血糖，並且能治療失眠。",
        "metadata": {
            "product_name": "XX膠囊",
            "date": "2023-11-20",
            "law": "食安法第28條",
            "industry": "Food",
            "tag_name": "醫療效能", # 對應 Tag
            "link": "https://example.com/case/002",
            "explanation": "提及改善糖尿病與治療失眠，非藥品不得為醫療效能之標示。"
        }
    },
    {
        "id": "case_003",
        "text": "使用本產品後，三天內罩杯升級，讓您重拾自信。",
        "metadata": {
            "product_name": "XX豐胸霜",
            "date": "2024-02-10",
            "law": "化妝品衛生安全管理法",
            "industry": "Cosmetic",
            "tag_name": "豐胸",
            "link": "https://example.com/case/003",
            "explanation": "化妝品不得宣稱更改生理結構或醫療效能。"
        }
    }
]

print("🚀 開始灌入資料...")

# 4. 迴圈處理：轉向量 -> 上傳
for case in mock_cases:
    print(f"正在處理: {case['metadata']['product_name']}...")
    
    # A. 呼叫 Gemini 轉向量 (768維)
    # 注意：這裡用的 model 必須跟 logic.py 裡的一模一樣
    response = genai.embed_content(
        model="models/text-embedding-004",
        content=case["text"],
        task_type="retrieval_document" # 存入時用 document，查詢時用 query
    )
    embedding = response['embedding']
    
    # B. 上傳到 Pinecone
    # 格式: (ID, Vector, Metadata)
    index.upsert(vectors=[
        (case["id"], embedding, case["metadata"])
    ])
    
    # 避免打 API 太快被 Google 擋，休息一下
    time.sleep(1)

print("✅ 資料灌入完成！Pinecone 現在有書可以查了。")
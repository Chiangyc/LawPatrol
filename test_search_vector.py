# test_search_vector.py
from database import search_vector_cases

if __name__ == "__main__":
    user_text = "本產品能幫助改善睡眠品質，讓你一夜好眠。"
    tag_name = "睡眠情緒"   # 用你 TAG_MAPPING / SQL_TO_TAG_MAP 裡真的有的中文 Tag

    results = search_vector_cases(user_text, tag_name, top_k=3)
    print("搜尋結果：")
    for r in results:
        print("-" * 40)
        print("case_id:", r["case_id"])
        print("product_name:", r["product_name"])
        print("law:", r["law"])
        print("date:", r["date"])
        print("link:", r["link"])
        print("similarity_score:", r["similarity_score"])

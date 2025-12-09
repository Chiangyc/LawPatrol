 # 找違規字詞在原文的哪裡

from typing import List, Dict

def find_text_indices(full_text: str, search_word: str) -> List[Dict[str, int]]:
    """
    功能：在 full_text 中找出 search_word 出現的「所有」位置
    用途：前端畫紅線需要準確的 start_index 和 end_index
    """
    indices = []
    
    # 1. 防呆：如果關鍵字是空的，或者原文是空的，直接回傳空陣列
    if not search_word or not full_text:
        return indices

    # 2. 移除關鍵字前後可能多餘的空白 (AI 有時候會多給空白)
    search_word = search_word.strip()

    # 3. 使用 Python 的 find 迴圈找字
    start = 0
    while True:
        # 從 start 的位置開始往後找
        idx = full_text.find(search_word, start)
        
        # 找不到就跳出迴圈
        if idx == -1:
            break
            
        # 找到了，計算結束位置
        end = idx + len(search_word)
        indices.append({"start": idx, "end": end})
        
        # 更新 start，準備找下一個 (避免無窮迴圈)
        start = end
        
    return indices

# ==========================================
# 4. 單元測試區 (直接執行 python utils.py)
# ==========================================
if __name__ == "__main__":
    # 模擬使用者在 Google Docs 選取的文字
    text = "這款產品能幫你甩油，保證三天甩油成功，真的能甩油嗎？"
    
    # 模擬 AI 抓出來的違規詞
    keyword = "甩油"
    
    print(f"測試文字: {text}")
    print(f"尋找關鍵字: {keyword}")
    
    result = find_text_indices(text, keyword)
    print(f"結果: {result}")
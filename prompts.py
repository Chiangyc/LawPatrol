# ==========================================
# 定義 Prompt 模板與分類結構
# ==========================================

# 這些分類必須跟 database.py 的 TAG_MAPPING 邏輯一致
TAG_CATEGORIES = {
    "提及醫療與治療行為": [
        "治療", "症狀緩解", "預防", "痊癒", "消腫", 
        "矯正復健", "療法", "傷口護理"
    ],
    "宣稱生理機能改變": [
        "再生抗老", "增生", "活化機能", "燃脂瘦身", "排毒解酒", 
        "拉提緊緻", "生髮育髮", "豐胸", "長高發育", "生殖機能", 
        "睡眠情緒", "免疫體質"
    ],
    "語氣過度誇大與絕對": [
        "唯一第一", "完全永久", "奇蹟神效", "保證承諾", "立即速效"
    ],
    "提及權威與高風險疾病": [
        "臨床實驗", "醫師專家", "見證推薦", "癌症", "三高心血管", "發炎"
    ]
}

def get_formatted_tags_prompt():
    """將 Tag 分類轉為 Prompt 字串"""
    prompt_text = ""
    for category, tags in TAG_CATEGORIES.items():
        prompt_text += f"- 【{category}】: {', '.join(tags)}\n"
    return prompt_text

# --- Step 1: 抓出產業與違規詞 ---
STEP1_PROMPT_TEMPLATE = """
你是一個台灣廣告法規審查員。請分析使用者的輸入文字。

任務：
1. 辨識產業類別 (Industry)，僅限以下四種：Food(食品), Cosmetic(化妝品), Medicine(藥品), Device(醫療器材)。

2. 檢查使用者的文案內容，是否**涉及或隱喻**以下違規主題 (Tags)。
   請參考以下「違規分類」來進行判斷，即使沒有出現完全一樣的關鍵字，只要**語意符合該分類下的概念**，也請列出。

違規主題列表 (依分類)：
{tags_context_str}

⚠️ 重要規則（很重要，務必遵守）：
- 你**只能**從上面列表中的標籤中選擇 "tag" 的值，
  例如：「治療」、「症狀緩解」、「燃脂瘦身」、「癌症」、「三高心血管」、「發炎」…等。
- 絕對**不可以創造新的標籤名稱**，
  例如「高風險疾病」、「疾病風險」、「慢性病」、「嚴重疾病」這類沒有出現在列表中的字，一律禁止使用。
- 當文案提到特定疾病（例如糖尿病、高血壓、高血脂等）時：
  - 如果合理屬於你看到的標籤（例如與心血管、血壓、血脂、血糖、動脈硬化等相關），可以使用「三高心血管」；
  - 如果無法合理歸入任何現有標籤，就不要硬套，直接**不要為這一段產生 tag**。
- 如果沒有發現違規或無法對應任何標籤，identified_tags 可以是空陣列 []。

3. 針對每個偵測到的標籤，找出原文中觸發該標籤的「確切字詞」(trigger_words)。
   注意：trigger_words 必須是原文中真實出現的字串。

Input Text:
{user_text}

Output JSON Format:
{{
  "industry": "Food",
  "identified_tags": [
    {{
      "tag": "燃脂瘦身", 
      "trigger_words": ["甩油", "暴瘦"]
    }}
  ]
}}
如果沒有發現違規，identified_tags 請回傳空陣列 []。
"""



# --- Step 3: 綜合分析與建議 ---
STEP3_PROMPT_TEMPLATE = """
你是一個專業的法規顧問。
我們已經初步偵測到使用者文案有違規風險，並從資料庫檢索了相似的裁罰案例。

任務：
請根據「檢索到的案例」與「法規知識」，針對每一個違規詞 (trigger_word) 提供分析與修改建議。

Input Information:
1. User Original Text: {user_text}
2. Identified Tags & Words: {step1_result}
3. Retrieved Reference Cases (Evidence): {vector_results}

Output JSON Format:
{{
  "analysis_results": [
    {{
      "trigger_word": "甩油",
      "tag": "燃脂瘦身",
      "reason": "說明為什麼違規 (請引用相關法規)...",
      "suggestion": "給出具體修改建議 (例如改為「促進代謝」)...",
      "reference_cases": [
         {{ 
            "product_name": "XX綠茶", 
            "date": "2023-10" 
         }} 
         // 請從 Input 的 Evidence 中挑選 1-2 則最相關的案例
      ]
    }}
  ]
}}
"""
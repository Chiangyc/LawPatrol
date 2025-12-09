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


# --- Step 1: 抓出產業與違規詞（精簡版） ---
STEP1_PROMPT_TEMPLATE = """
你是一名台灣廣告法規審查員，請以 JSON 回覆。

任務：
1. 判斷產業類別 industry，只能是下面四種其中之一：
   - Food (食品)
   - Cosmetic (化妝品)
   - Medicine (藥品)
   - Device (醫療器材)

2. 檢查文案是否「涉及或隱喻」下列違規主題 (Tags)。
   只要語意明顯對應即可，不一定要出現完全相同字詞。

違規主題列表：
{tags_context_str}

規則（務必遵守）：
- "tag" 只能使用上面列表中出現過的標籤名稱
  （例如：「治療」「症狀緩解」「燃脂瘦身」「癌症」「三高心血管」「發炎」等），
  絕對禁止創造任何新的標籤名稱。
- 若文案提到具體疾病（如糖尿病、高血壓、高血脂等），
  只有在合理屬於心血管或三高相關時，才可以用「三高心血管」；
  若無法合理歸類，就不要為這部分產生任何 tag。
- 若沒有發現違規或無法對應任何標籤，identified_tags 請回傳空陣列 []。

3. 對每個偵測到的標籤，列出原文中觸發該標籤的確切字詞 trigger_words，
   這些字串必須真實存在於原始文案中。

Input Text:
{user_text}

Output JSON 範例：
{{
  "industry": "Food",
  "identified_tags": [
    {{
      "tag": "燃脂瘦身",
      "trigger_words": ["甩油", "暴瘦"]
    }}
  ]
}}
如果沒有發現違規，identified_tags 請回傳 []。
"""

# --- Step 3: 綜合分析與建議（精簡版，suggestion 直接給改寫句子） ---
# --- Step 3: 綜合分析與建議（精簡版，全句 suggestion） ---
STEP3_PROMPT_TEMPLATE = """
你是一名廣告法規顧問，請根據下列資訊產生違規原因、可能觸犯的法律，以及「整句改寫後文案」，並以 JSON 回覆。

任務：
- 對每一個違規詞 trigger_word：
  - reason：簡短說明為什麼可能違反台灣相關法規，可引用法條或原則。
  - law：請盡量用簡短文字指出可能觸犯的法律依據（例如：「食品安全衛生管理法第28條」、「藥事法第68條」等），若無法確定條號，可寫成「食品安全衛生管理法相關規定」之類的描述。
  - reference_cases：儘量從提供的裁罰案例中挑選 1–2 則最相關的案例放入， 每筆只需包含 product_name 與 date。

- 此外，請回傳一個整體的 suggestion：
  - suggestion：請將「整段原始文案」改寫成一個合法且保守的版本。
  - 內容要是可以直接貼回廣告的完整句子，不要再出現「建議改為…」「可以修改成…」等指令語氣。

Input：
1. User Original Text: {user_text}
2. Identified Tags & Words: {step1_result}
3. Retrieved Reference Cases: {vector_results}

Output JSON 範例：
{{
  "analysis_results": [
    {{
      "trigger_word": "甩油",
      "tag": "燃脂瘦身",
      "reason": "說明該詞如何涉及誇大或醫療效能，以及相關法規依據。",
      "law": "食品安全衛生管理法第28條",
      "reference_cases": [
        {{
          "product_name": "XX綠茶",
          "date": "2023-10"
        }}
      ]
    }}
  ],
  "suggestion": "本產品含膳食纖維與多種營養成分，有助維持正常代謝與健康體態。"
}}
"""


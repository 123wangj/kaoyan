"""
检查PDF中的题目是否与现有题库匹配
"""
import pdfplumber
import json
import re

# 加载现有题库
existing_questions = {}
with open(r'c:\Users\wang\Desktop\考研学习\data\question_bank.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        q = json.loads(line)
        # 用前60字符作为指纹
        fingerprint = q['content'][:60].strip().replace(' ', '').replace('\n', '')
        if q['subject'] not in existing_questions:
            existing_questions[q['subject']] = {}
        existing_questions[q['subject']][fingerprint] = q

# 从数据结构PDF提取题目并匹配
pdf_path = r'c:\Users\wang\Desktop\考研学习\tiku\2025王道数据结构选择题_含答案与解析.pdf'
pdf = pdfplumber.open(pdf_path)

matched = 0
unmatched = 0
unmatched_samples = []

for page_num in range(len(pdf.pages)):
    text = pdf.pages[page_num].extract_text()
    if not text:
        continue
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    for line in lines:
        q_match = re.match(r'^(\d+)[\.\s]+(.+)', line)
        if q_match and not re.match(r'^[A-D][\.\s]', line) and '答案' not in line and '解析' not in line:
            q_text = q_match.group(2).strip()[:60].replace(' ', '').replace('\n', '')
            
            if '数据结构' in existing_questions:
                found = None
                for fp, q_data in existing_questions['数据结构'].items():
                    # 模糊匹配
                    if len(q_text) >= 20 and len(fp) >= 20:
                        if q_text[:30] == fp[:30]:
                            found = q_data
                            break
                if found:
                    matched += 1
                else:
                    unmatched += 1
                    if len(unmatched_samples) < 5:
                        unmatched_samples.append(q_text[:80])

pdf.close()

print(f"数据结构: 匹配={matched}, 未匹配={unmatched}")
print(f"未匹配样例:")
for s in unmatched_samples:
    print(f"  {s}")
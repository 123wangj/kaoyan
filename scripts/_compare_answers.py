"""
比较PDF提取的答案与现有question_bank.jsonl的答案
看看PDF中的答案是否正确
"""
import pdfplumber
import json
import re
from pathlib import Path

# 先加载现有题库的答案
existing = {}
with open(r'c:\Users\wang\Desktop\考研学习\data\question_bank.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        q = json.loads(line)
        key = (q['subject'], q['content'][:50])  # 用前50字作为匹配键
        existing[key] = q['answer']

# 从组成原理PDF提取答案
pdf_path = r'c:\Users\wang\Desktop\考研学习\tiku\2025王道计算机组成原理选择题_含答案与解析.pdf'
pdf = pdfplumber.open(pdf_path)

match_count = 0
mismatch_count = 0
not_found = 0
mismatches = []

for page_num in range(len(pdf.pages)):
    text = pdf.pages[page_num].extract_text()
    if not text:
        continue
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    i = 0
    while i < len(lines):
        line = lines[i]
        # 找题目起始
        q_match = re.match(r'^(\d+)[\.\s]+(.+)', line)
        if q_match and not re.match(r'^[A-D][\.\s]', line) and '答案' not in line:
            q_text = q_match.group(2).strip()[:80]
            
            # 找后面的答案
            answer = None
            j = i + 1
            while j < len(lines) and j < i + 20:
                ans_match = re.match(r'【答案】([A-D])', lines[j])
                if ans_match:
                    answer = ans_match.group(1)
                    break
                # 如果遇到下一个题目，停止
                if re.match(r'^\d+[\.\s]+', lines[j]) and '答案' not in lines[j]:
                    break
                j += 1
            
            if answer:
                # 在现有题库中找匹配
                found = False
                for (subj, content_key), existing_ans in existing.items():
                    if subj == '计算机组成原理' and q_text[:30] in content_key:
                        found = True
                        if answer == existing_ans:
                            match_count += 1
                        else:
                            mismatch_count += 1
                            if len(mismatches) < 10:
                                mismatches.append((q_text[:80], answer, existing_ans))
                        break
                if not found:
                    not_found += 1
        i += 1

pdf.close()

print(f"组成原理答案对比:")
print(f"  匹配: {match_count}")
print(f"  不匹配: {mismatch_count}")
print(f"  未找到: {not_found}")
print(f"\n不匹配样例:")
for q, pdf_ans, existing_ans in mismatches:
    print(f"  Q: {q}")
    print(f"    PDF: {pdf_ans} | 现有: {existing_ans}")
    print()
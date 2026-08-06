"""
检查PDF中答案与解析的组织形式 - 是按题目穿插还是集中放在末尾
"""
import pdfplumber
import re

# 检查数据结构PDF
pdf_path = r'c:\Users\wang\Desktop\考研学习\tiku\2025王道数据结构选择题_含答案与解析.pdf'
pdf = pdfplumber.open(pdf_path)

# 找"答案与解析"标题
for page_num in range(len(pdf.pages)):
    text = pdf.pages[page_num].extract_text()
    if not text:
        continue
    if '答案与解析' in text or '参考答案' in text:
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        print(f"\n=== Page {page_num+1} - Found '答案与解析' ===")
        for i, l in enumerate(lines[:30]):
            print(f"  [{i}] {l[:200]}")
        break

# 也检查是否有分散的答案
print("\n\n=== Scanning for answer patterns across pages ===")
answer_pages = []
for page_num in range(len(pdf.pages)):
    text = pdf.pages[page_num].extract_text()
    if not text:
        continue
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    has_q = any(re.match(r'^\d+[\.\s]', l) and not '答案' in l for l in lines)
    has_a = any('【答案】' in l for l in lines)
    if has_q and has_a:
        answer_pages.append(page_num + 1)

print(f"Pages with both questions and answers: {len(answer_pages)}")
print(f"Sample: {answer_pages[:10]}...")

# 检查是否所有有问题的页面都有答案
q_only_pages = []
for page_num in range(len(pdf.pages)):
    text = pdf.pages[page_num].extract_text()
    if not text:
        continue
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    has_q = any(re.match(r'^\d+[\.\s]', l) and not '答案' in l for l in lines)
    has_a = any('【答案】' in l for l in lines)
    if has_q and not has_a:
        q_only_pages.append(page_num + 1)

print(f"Pages with questions but NO answers: {len(q_only_pages)}")
print(f"Sample: {q_only_pages[:20]}...")

pdf.close()
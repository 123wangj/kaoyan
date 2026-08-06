"""
临时脚本：检查PDF前几页的完整结构
"""
import pdfplumber
import re

pdf_path = r'c:\Users\wang\Desktop\考研学习\tiku\2025王道数据结构选择题_含答案与解析.pdf'
pdf = pdfplumber.open(pdf_path)

# 先看前10页（跳过目录页）
for page_num in range(0, 10):
    text = pdf.pages[page_num].extract_text()
    if not text:
        print(f"\n=== Page {page_num+1} EMPTY ===")
        continue
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    print(f"\n=== Page {page_num+1} ({len(lines)} lines) ===")
    for i, l in enumerate(lines[:60]):
        marker = ""
        if '答案' in l:
            marker = " <<< ANSWER"
        if '解析' in l:
            marker = " <<< EXPLANATION"
        if re.match(r'^\d+[\.\．]', l):
            marker = " <<< QUESTION"
        if re.match(r'^[A-D][\.\．]', l):
            marker = " <<< OPTION"
        print(f"  [{i}]{marker} {l[:120]}")

pdf.close()
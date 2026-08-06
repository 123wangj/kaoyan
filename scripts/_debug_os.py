"""
临时脚本：检查OS PDF答案对齐情况
"""
import pdfplumber
import re

pdf_path = r'c:\Users\wang\Desktop\考研学习\tiku\2025王道操作系统选择题 _含答案与解析.pdf'
pdf = pdfplumber.open(pdf_path)

for page_num in range(2, 8):
    text = pdf.pages[page_num].extract_text()
    if not text:
        continue
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    print(f"\n=== Page {page_num+1} ===")
    for i, l in enumerate(lines[:80]):
        if re.match(r'^\d+[\.\s]', l) or '答案' in l or '解析' in l:
            print(f"  [{i}] {l[:200]}")

pdf.close()
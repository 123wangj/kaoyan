"""
临时脚本：检查PDF中答案和解析的文本结构
"""
import pdfplumber
import re

pdf_path = r'c:\Users\wang\Desktop\考研学习\tiku\2025王道数据结构选择题_含答案与解析.pdf'
pdf = pdfplumber.open(pdf_path)

# 扫描所有页面，寻找答案/解析区域
for page_num in range(len(pdf.pages)):
    text = pdf.pages[page_num].extract_text()
    if not text:
        continue
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    # 检查是否有"答案"或"解析"关键词
    has_answer = any('答案' in l or '解析' in l or '参考答案' in l for l in lines)
    if has_answer:
        print(f"\n=== Page {page_num+1} (has answer/explanation marker) ===")
        for i, l in enumerate(lines[:50]):
            print(f"  [{i}] {l}")
        print("...")
        if page_num >= 5:
            break

# 再看看最后几页（通常答案集中在最后）
print("\n\n=== Last 5 pages ===")
for page_num in range(max(0, len(pdf.pages)-5), len(pdf.pages)):
    text = pdf.pages[page_num].extract_text()
    if not text:
        continue
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    print(f"\n--- Page {page_num+1} ---")
    for i, l in enumerate(lines[:40]):
        print(f"  [{i}] {l}")

pdf.close()
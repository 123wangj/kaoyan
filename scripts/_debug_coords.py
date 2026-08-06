"""
检查组成原理PDF中文本的坐标顺序
"""
import pdfplumber

pdf_path = r'c:\Users\wang\Desktop\考研学习\tiku\2025王道计算机组成原理选择题_含答案与解析.pdf'
pdf = pdfplumber.open(pdf_path)

page = pdf.pages[4]  # page 5 (0-indexed: 4)

# 按x坐标排序提取
words = page.extract_words()
# 按y坐标分组
y_groups = {}
for w in words:
    y_key = round(w['top'], 0)
    if y_key not in y_groups:
        y_groups[y_key] = []
    y_groups[y_key].append(w)

# 按y排序，然后每个y组内按x排序
for y in sorted(y_groups.keys())[:30]:
    group = sorted(y_groups[y], key=lambda w: w['x0'])
    text = ' '.join(w['text'] for w in group)
    print(f"y={y:.0f}: {text[:200]}")

pdf.close()
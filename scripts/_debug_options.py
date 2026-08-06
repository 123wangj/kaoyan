"""Debug option extraction"""
import pdfplumber
import re

pdf = pdfplumber.open(r'c:\Users\wang\Desktop\考研学习\tiku\2025王道数据结构选择题_含答案与解析.pdf')
text = pdf.pages[0].extract_text()
lines = [l.strip() for l in text.split('\n') if l.strip()]

print(f"Total lines: {len(lines)}")
for i, l in enumerate(lines[:15]):
    marker = ""
    if re.match(r'^\d+[\.\s]', l) and not re.match(r'^[A-D][\.\s]', l): marker = " [Q]"
    if '【答案】' in l: marker = " [ANS]"
    if '【解析】' in l: marker = " [EXP]"
    print(f"  [{i}]{marker} {l[:120]}")

# 找到第一个【答案】
ans_idx = None
for i, l in enumerate(lines):
    if '【答案】' in l:
        ans_idx = i
        print(f"\nFirst answer at line {i}: {l}")
        break

if ans_idx is None:
    print("No answer found!")
    pdf.close()
    exit()

# 找到第一个题目
q_start_idx = None
for j in range(ans_idx - 1, -1, -1):
    l = lines[j]
    is_q = re.match(r'^\d+[\.\s]', l)
    is_opt = re.match(r'^[A-D][\.\s]', l)
    print(f"  Checking line {j}: is_q={bool(is_q)}, is_opt={bool(is_opt)}, text={l[:80]}")
    if is_q and not is_opt:
        q_start_idx = j
        print(f"  Found question at line {j}")
        break

if q_start_idx is None:
    print("No question found!")
    pdf.close()
    exit()

# 收集题目文本
q_text_parts = []
for j in range(q_start_idx, ans_idx):
    l = lines[j].strip()
    if j == q_start_idx:
        q_match = re.match(r'^\d+[\.\s]+(.+)', l)
        if q_match:
            l = q_match.group(1)
    q_text_parts.append(l)

full_text = ' '.join(q_text_parts).strip()
full_text = re.sub(r'\s+', ' ', full_text)

print(f"\nFull text: [{full_text[:300]}]")

# Test the split function
opt_pattern = re.compile(r'\s+([A-D])[\.\．\、\s]\s*')
matches = list(opt_pattern.finditer(full_text))
print(f"\nFound {len(matches)} option matches:")
for m in matches:
    ctx_start = max(0, m.start()-5)
    ctx_end = min(len(full_text), m.end()+20)
    print(f"  Group(1)='{m.group(1)}', context='{full_text[ctx_start:ctx_end]}'")

opt_parts = opt_pattern.split(full_text)
print(f"\nSplit parts ({len(opt_parts)}):")
for i, p in enumerate(opt_parts):
    print(f"  [{i}] '{p[:100]}'")

pdf.close()
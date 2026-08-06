# Generate final knowledge_points.jsonl with correct format for frontend
import json
import re
from pathlib import Path
from collections import Counter

DATA = Path("data")
# Read from a temp backup first, then write to knowledge_points.jsonl
INPUT = DATA / "knowledge_points.jsonl"
OUTPUT = DATA / "knowledge_points.jsonl"

# Read existing extracted data (format: title, content, tags, page)
kps = []
with open(INPUT, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line:
            kps.append(json.loads(line))

print(f"读取到 {len(kps)} 条原始知识点")

# Check format
if kps:
    print(f"格式字段: {list(kps[0].keys())}")

def chinese_ratio(text):
    if not text:
        return 0, 0
    chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    total = len(text)
    return chinese / max(total, 1), chinese

subject_map = {
    '数据结构': '数据结构',
    '计算机组成原理': '计算机组成原理',
    '计算机网络': '计算机网络',
}

transformed = []
id_counter = 1

for kp in kps:
    # Handle both tags (list) and subject (string) formats
    tags = kp.get('tags', kp.get('subject', ''))
    if isinstance(tags, list):
        subject = tags[0] if tags else ''
    else:
        subject = tags
    
    mapped_subject = subject_map.get(subject, '')
    if not mapped_subject:
        continue
    
    title = kp.get('title', '').strip()
    content = kp.get('content', '').strip()
    
    # Skip if content is too garbled
    ratio, chinese_cnt = chinese_ratio(content)
    if chinese_cnt < 8 or ratio < 0.15:
        continue
    
    # Clean title
    title_ratio, title_cn = chinese_ratio(title)
    if title_cn < 2 or title_ratio < 0.2:
        # Extract first meaningful sentence from content
        sentences = re.split(r'(?<=[。；])', content)
        title = ''
        for s in sentences:
            s_cn = sum(1 for c in s if '\u4e00' <= c <= '\u9fff')
            if s_cn >= 3:
                # Take first 35 chars starting with Chinese
                for i, c in enumerate(s):
                    if '\u4e00' <= c <= '\u9fff':
                        title = s[i:i+35]
                        break
                break
        if not title or sum(1 for c in title if '\u4e00' <= c <= '\u9fff') < 2:
            continue
    
    # Clean content
    content = content.strip()
    while content and not ('\u4e00' <= content[0] <= '\u9fff' or content[0].isalnum()):
        content = content[1:]
    while content and not ('\u4e00' <= content[-1] <= '\u9fff' or content[-1].isalnum()):
        content = content[:-1]
    
    if len(content) < 10:
        continue
    
    transformed.append({
        "id": f"kp_{id_counter:04d}",
        "title": title[:50],
        "content": content,
        "subject": mapped_subject,
        "page": kp.get('page', 1),
    })
    id_counter += 1

# Deduplicate
seen = set()
final = []
for kp in transformed:
    key = kp['content'][:50]
    if key not in seen:
        seen.add(key)
        final.append(kp)

# Write output
with open(OUTPUT, 'w', encoding='utf-8') as f:
    for kp in final:
        f.write(json.dumps(kp, ensure_ascii=False) + '\n')

print(f"\n转换完成: {len(final)} 个知识点")
print(f"已保存至: {OUTPUT}")

subjects = Counter(kp['subject'] for kp in final)
for s, c in subjects.most_common():
    print(f"  {s}: {c}个")

print(f"\n前10个样例:")
for kp in final[:10]:
    c = kp['content'][:60]
    print(f"  [{kp['subject']}] {kp['id']}: {kp['title'][:40]}")
    print(f"    内容: {c}...")
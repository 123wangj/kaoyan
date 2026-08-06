import json
from pathlib import Path
from collections import Counter

data = Path('data') / 'knowledge_points.jsonl'
kps = []
with open(data, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                kps.append(json.loads(line))
            except:
                pass

print(f'知识点总数: {len(kps)}')
tags = Counter()
for kp in kps:
    for t in kp.get('tags', []):
        tags[t] += 1
for tag, count in tags.most_common():
    print(f'  {tag}: {count}个')

print()
if kps:
    print('前5个知识点:')
    for kp in kps[:5]:
        title = kp['title'][:50]
        content = kp['content'][:60]
        tag = kp['tags'][0]
        print(f'  [{tag}] {title}')
        print(f'    内容: {content}...')
else:
    print('没有知识点')
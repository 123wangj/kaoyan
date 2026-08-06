#!/usr/bin/env bash
TOKEN=$(curl -sk -X POST https://www.sx01bit.cn/api/auth/login -H "Content-Type: application/json" -d '{"user_id":"sx01_001","password":"KaoYan@2026"}' | python -c "import json,sys;print(json.load(sys.stdin).get('token',''))")
curl -sk -H "Authorization: Bearer $TOKEN" https://www.sx01bit.cn/question-bank/all -o /tmp/qb.json
python -c "
import json
d = json.load(open('/tmp/qb.json'))
print(f'Total: {len(d)}')
# 统计 subject
from collections import Counter
c = Counter(q.get('subject','(no subject)') for q in d)
print('subject 分布:')
for s, n in c.most_common():
    print(f'  {s!r:30s} {n}')
# 有 subject 但 year 缺失的
no_year = [q for q in d if not q.get('year') and not any(y in (q.get('content') or '') for y in ['2024','2023','2022','2021','2020'])]
print(f'无 year 且 content 无年份: {len(no_year)}')
# 有 type 缺失
no_type = [q for q in d if not q.get('type')]
print(f'无 type: {len(no_type)}')
# 有 id 缺失
no_id = [q for q in d if not q.get('id')]
print(f'无 id: {len(no_id)}')
# id 重复
ids = [q.get('id') for q in d]
from collections import Counter
ic = Counter(ids)
dups = [(k,v) for k,v in ic.items() if v>1]
print(f'重复 id 数: {len(dups)} (前 3 个: {dups[:3]})')
print('---')
print('前 2 题字段(完整):')
import json as j
print(j.dumps(d[0], ensure_ascii=False, indent=2)[:400])
print('---')
print(j.dumps(d[1], ensure_ascii=False, indent=2)[:400])
"

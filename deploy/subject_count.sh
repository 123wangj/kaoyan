#!/usr/bin/env bash
docker exec kaoyan-ai-app python -c "
import json
subs = {}
files = ['/app/data/question_bank.jsonl','/app/data/question_bank_mcq.jsonl','/app/data/question_bank_updated.jsonl','/app/data/question_bank_big.jsonl']
for f in files:
    try:
        for line in open(f, encoding='utf-8'):
            q = json.loads(line)
            s = q.get('subject','')
            subs[s] = subs.get(s, 0) + 1
    except Exception as e:
        print(f'err {f}: {e}')
print('=== subject 字段统计(所有 jsonl)===')
for s, c in sorted(subs.items(), key=lambda x: -x[1]):
    print(f'  {repr(s):30s} {c}')
"

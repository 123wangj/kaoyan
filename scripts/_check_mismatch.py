import json
with open(r'c:\Users\wang\Desktop\考研学习\data\question_bank.jsonl', 'r', encoding='utf-8') as f:
    qs = [json.loads(line) for line in f]

mismatches = 0
total_checked = 0
for q in qs:
    if q['answer'] and len(q['options']) >= 3:
        total_checked += 1
        expected = q['answer'] + '.'
        idx = ord(q['answer']) - ord('A')
        if idx < len(q['options']):
            opt = q['options'][idx]
            if not opt.startswith(expected):
                mismatches += 1
                if mismatches <= 10:
                    print(f'  [{q["subject"]}] Q{q["question_number"]}: answer={q["answer"]}, opt[{idx}]={opt[:50]}')
                    print(f'    All options: {q["options"]}')
                    print()

print(f'Mismatches (>=3 options): {mismatches}/{total_checked}')
import json

with open(r'c:\Users\wang\Desktop\考研学习\data\question_bank_new.jsonl', 'r', encoding='utf-8') as f:
    qs = [json.loads(line) for line in f]

for subj in ['数据结构', '操作系统', '计算机组成原理', '计算机网络']:
    sqs = [q for q in qs if q['subject'] == subj]
    chapters = set(q['chapter'] for q in sqs if q['chapter'])
    sections = set(q['section'] for q in sqs if q['section'])
    print(f"{subj}: {len(sqs)} questions")
    print(f"  With chapter: {sum(1 for q in sqs if q['chapter'])}")
    print(f"  Chapters: {sorted(chapters)}")
    print(f"  With section: {sum(1 for q in sqs if q['section'])}")
    print(f"  Sections: {sorted(sections)}")
    print()
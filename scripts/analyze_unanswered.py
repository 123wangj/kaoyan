# -*- coding: utf-8 -*-
import json, sys
sys.stdout.reconfigure(encoding='utf-8')

no_explanation = []
with open('data/question_bank_mcq.jsonl', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        obj = json.loads(line.strip())
        if obj.get('is_real_exam') and not obj.get('explanation'):
            no_explanation.append((i, obj))

print('Total:', len(no_explanation))

# By source
sources = {}
for idx, obj in no_explanation:
    src = obj.get('source', 'unknown')
    sources[src] = sources.get(src, 0) + 1
print('\nBy source:')
for s, c in sorted(sources.items()):
    print('  %s: %d' % (s, c))

# By subject
subjects = {}
for idx, obj in no_explanation:
    subj = obj.get('subject', 'unknown')
    subjects[subj] = subjects.get(subj, 0) + 1
print('\nBy subject:')
for s, c in sorted(subjects.items()):
    print('  %s: %d' % (s, c))

# Check answer status
has_answer = sum(1 for _, o in no_explanation if o.get('answer'))
no_answer = sum(1 for _, o in no_explanation if not o.get('answer'))
print('\nHas answer: %d, No answer: %d' % (has_answer, no_answer))

# Sample first 5
print('\n--- Sample questions ---')
for idx, obj in no_explanation[:5]:
    qid = obj.get('id')
    subj = obj.get('subject')
    content = obj.get('content', '')[:120]
    options = obj.get('options')
    answer = obj.get('answer', 'EMPTY')
    chapter = obj.get('chapter')
    section = obj.get('section')
    source = obj.get('source')
    print('\nLine %d | ID: %s | Subject: %s' % (idx, qid, subj))
    print('Content: %s' % content)
    print('Options: %s' % options)
    print('Answer: %s' % answer)
    print('Chapter: %s | Section: %s' % (chapter, section))
    print('Source: %s' % source)

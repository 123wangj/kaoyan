# -*- coding: utf-8 -*-
"""按科目拆分待解析题目"""
import json, sys, os
sys.stdout.reconfigure(encoding='utf-8')

subjects = {
    '数据结构': [],
    '计算机组成原理': [],
    '操作系统': [],
    '计算机网络': []
}

with open('data/question_bank_mcq.jsonl', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        obj = json.loads(line.strip())
        if obj.get('is_real_exam') and not obj.get('explanation'):
            subj = obj.get('subject', '')
            obj['_line_number'] = i  # Track line number for later merge
            if subj in subjects:
                subjects[subj].append(obj)

outdir = r'C:\Users\wang\.qoderwork\workspace\mq15g1pwu9uz7cxc'
name_map = {'数据结构': 'ds', '计算机组成原理': 'co', '操作系统': 'os', '计算机网络': 'net'}
for subj, questions in subjects.items():
    fname = 'batch_' + name_map[subj] + '.json'
    path = os.path.join(outdir, fname)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)
    print('%s: %d questions -> %s' % (subj, len(questions), path))

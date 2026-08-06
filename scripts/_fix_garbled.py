"""将旧题库中匹配的题目内容替换到新题库中，修复乱码题目"""
import json

with open(r'c:\Users\wang\Desktop\考研学习\data\question_bank_new.jsonl', 'r', encoding='utf-8') as f:
    new_qs = [json.loads(line) for line in f]

with open(r'c:\Users\wang\Desktop\考研学习\data\question_bank.jsonl', 'r', encoding='utf-8') as f:
    old_qs = [json.loads(line) for line in f]

# 为旧题库建立索引：按学科和题目内容前20字符
old_index = {}
for oq in old_qs:
    key = (oq['subject'], oq['content'][:30].replace(' ', ''))
    # 也按答案和选项数量建立辅助索引
    if key not in old_index:
        old_index[key] = []
    old_index[key].append(oq)

fixed = 0
for nq in new_qs:
    if len(nq['options']) >= 3:
        continue  # 已经有足够选项，跳过
    
    # 尝试匹配旧题库
    nq_content_prefix = nq['content'][:30].replace(' ', '')
    nq_answer = nq['answer']
    
    best_match = None
    
    # 搜索所有旧题
    for oq in old_qs:
        if oq['subject'] != nq['subject']:
            continue
        if oq['answer'] != nq_answer:
            continue
        
        # 计算内容相似度
        oq_prefix = oq['content'][:30].replace(' ', '')
        
        # 提取新题中的可读字符
        readable_chars = set(c for c in nq_content_prefix if ord(c) < 0x4e00 or ord(c) > 0x9fff)
        # 实际上中文是0x4e00-0x9fff，可读的应该是这个范围
        # 乱码字符在CJK扩展区（>0x9fff）或私有区
        
        # 简单方法：检查共同中文字符
        nq_chinese = set(c for c in nq_content_prefix if '\u4e00' <= c <= '\u9fff')
        oq_chinese = set(c for c in oq_prefix if '\u4e00' <= c <= '\u9fff')
        
        if nq_chinese and oq_chinese:
            common = nq_chinese & oq_chinese
            if len(common) >= min(len(nq_chinese), len(oq_chinese)) * 0.5:
                best_match = oq
                break
    
    if best_match:
        nq['content'] = best_match['content']
        nq['options'] = best_match['options']
        nq['explanation'] = best_match['explanation']
        nq['source'] = best_match.get('source', '')
        nq['is_real_exam'] = best_match.get('is_real_exam', False)
        if best_match.get('knowledge_points'):
            nq['knowledge_points'] = best_match['knowledge_points']
        fixed += 1

print(f"Fixed {fixed} questions from old bank")

# 保存
with open(r'c:\Users\wang\Desktop\考研学习\data\question_bank_new.jsonl', 'w', encoding='utf-8') as f:
    for q in new_qs:
        f.write(json.dumps(q, ensure_ascii=False) + '\n')

print(f"Saved {len(new_qs)} questions")

# 重新统计
garbled = [q for q in new_qs if len(q['options']) < 3]
print(f"Remaining garbled: {len(garbled)}")
for q in garbled[:5]:
    print(f"  [{q['subject']}] Q{q['question_number']}: {q['content'][:80]}")
    print(f"    Options: {q['options']}")
    print(f"    Answer: {q['answer']}")
import json

with open(r'c:\Users\wang\Desktop\考研学习\data\question_bank_new.jsonl', 'r', encoding='utf-8') as f:
    new_qs = [json.loads(line) for line in f]

with open(r'c:\Users\wang\Desktop\考研学习\data\question_bank.jsonl', 'r', encoding='utf-8') as f:
    old_qs = [json.loads(line) for line in f]

garbled = [q for q in new_qs if len(q['options']) < 3]
print(f"Garbled questions (<3 options): {len(garbled)}")

# 按学科统计
for subj in ['数据结构', '操作系统', '计算机组成原理', '计算机网络']:
    g = [q for q in garbled if q['subject'] == subj]
    print(f"  {subj}: {len(g)}")

# 尝试匹配旧题库
matched = 0
for gq in garbled:
    gq_content = gq['content']
    for oq in old_qs:
        # 用题目内容的前20个字符进行模糊匹配
        gq_prefix = gq_content[:20].replace(' ', '')
        oq_prefix = oq['content'][:20].replace(' ', '')
        if gq_prefix and oq_prefix and len(gq_prefix) >= 5:
            # 检查是否有共同字符
            common = sum(1 for c in gq_prefix if c in oq_prefix)
            if common >= min(len(gq_prefix), len(oq_prefix)) * 0.5:
                matched += 1
                break

print(f"\nMatched with old bank: {matched}/{len(garbled)}")

# 显示一个实际例子
print("\n=== 示例: 数据结构 Q3 ===")
ds3 = [q for q in new_qs if q['subject'] == '数据结构' and q['question_number'] == '3']
if ds3:
    q = ds3[0]
    print(f"Content: {q['content'][:150]}")
    print(f"Options: {q['options']}")
    print(f"Answer: {q['answer']}")
    print(f"Explanation: {q['explanation'][:150]}")
    
    # 在旧题库中找对应题目
    for oq in old_qs:
        if oq['subject'] == '数据结构' and '3' in str(oq.get('question_number', '')):
            print(f"\nOld Q: {oq['content'][:100]}")
            print(f"Old Options: {oq['options']}")
            print(f"Old Answer: {oq['answer']}")
            break
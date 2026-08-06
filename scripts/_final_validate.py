"""最终验证题库数据完整性"""
import json

with open(r'c:\Users\wang\Desktop\考研学习\data\question_bank.jsonl', 'r', encoding='utf-8') as f:
    qs = [json.loads(line) for line in f]

print("=" * 60)
print("题库最终验证报告")
print("=" * 60)
print(f"\n总题目数: {len(qs)}")

# 1. 按学科统计
print("\n--- 按学科统计 ---")
for subj in ['数据结构', '操作系统', '计算机组成原理', '计算机网络']:
    sqs = [q for q in qs if q['subject'] == subj]
    print(f"\n{subj}: {len(sqs)} 题")
    
    # 选项完整性
    has_4 = sum(1 for q in sqs if len(q['options']) == 4)
    has_3 = sum(1 for q in sqs if len(q['options']) == 3)
    has_lt3 = sum(1 for q in sqs if len(q['options']) < 3)
    print(f"  4选项: {has_4}, 3选项: {has_3}, <3选项: {has_lt3}")
    
    # 答案和解析
    has_answer = sum(1 for q in sqs if q['answer'])
    has_explanation = sum(1 for q in sqs if q['explanation'])
    print(f"  有答案: {has_answer}/{len(sqs)}, 有解析: {has_explanation}/{len(sqs)}")
    
    # 章节和小节
    has_chapter = sum(1 for q in sqs if q['chapter'])
    has_section = sum(1 for q in sqs if q['section'])
    print(f"  有章节: {has_chapter}/{len(sqs)}, 有小节: {has_section}/{len(sqs)}")
    
    # 真题标记
    is_real = sum(1 for q in sqs if q.get('is_real_exam'))
    print(f"  真题: {is_real}")

# 2. 选项完整性问题
print("\n--- 选项不足3个的题目 (共{}题) ---".format(
    sum(1 for q in qs if len(q['options']) < 3)))
for q in qs:
    if len(q['options']) < 3:
        print(f"  [{q['subject']}] Q{q['question_number']}: {q['content'][:60]}")
        print(f"    Options: {q['options']}")
        print(f"    Answer: {q['answer']}")

# 3. 选项与答案的对应性检查
print("\n--- 选项与答案对应性 ---")
mismatches = 0
for q in qs:
    if q['answer'] and len(q['options']) >= 1:
        expected = q['answer'] + '.'
        if len(q['options']) >= ord(q['answer']) - ord('A') + 1:
            opt = q['options'][ord(q['answer']) - ord('A')]
            if not opt.startswith(expected):
                mismatches += 1
                if mismatches <= 3:
                    print(f"  [{q['subject']}] Q{q['question_number']}: answer={q['answer']}, opt={opt[:40]}")
print(f"  选项与答案不匹配: {mismatches}")

# 4. 空内容检查
empty_content = [q for q in qs if not q['content']]
print(f"\n空内容: {len(empty_content)}")

# 5. 难度分布
print("\n--- 难度分布 ---")
for diff in ['基础', '中等', '困难']:
    count = sum(1 for q in qs if q.get('difficulty') == diff)
    print(f"  {diff}: {count}")

print("\n" + "=" * 60)
print("验证完成")
print("=" * 60)
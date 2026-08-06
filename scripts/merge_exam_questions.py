"""
将2024-2026年408真题合并到现有题库中。
"""
import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

def merge_exam_questions():
    # 读取现有题库
    existing_path = os.path.join(DATA_DIR, "question_bank_mcq.jsonl")
    existing = []
    existing_ids = set()
    if os.path.exists(existing_path):
        with open(existing_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    obj = json.loads(line)
                    existing.append(obj)
                    existing_ids.add(obj["id"])
    
    print(f"现有题库: {len(existing)} 道题")
    
    # 读取三年真题
    new_questions = []
    for year in ["2024", "2025", "2026"]:
        exam_path = os.path.join(DATA_DIR, f"exam_{year}.jsonl")
        if not os.path.exists(exam_path):
            print(f"警告: {exam_path} 不存在，跳过")
            continue
        
        with open(exam_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    obj = json.loads(line)
                    new_questions.append(obj)
    
    print(f"新增真题: {len(new_questions)} 道")
    
    # 去重（按ID）
    added = 0
    for q in new_questions:
        if q["id"] not in existing_ids:
            existing.append(q)
            existing_ids.add(q["id"])
            added += 1
    
    print(f"实际新增: {added} 道（去重后）")
    
    # 备份原文件
    backup_path = existing_path + ".bak_exam"
    if not os.path.exists(backup_path):
        import shutil
        shutil.copy2(existing_path, backup_path)
        print(f"已备份原文件到: {backup_path}")
    
    # 写入合并后的题库
    with open(existing_path, "w", encoding="utf-8") as f:
        for obj in existing:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    
    print(f"合并后题库: {len(existing)} 道题")
    
    # 统计
    exam_count = sum(1 for q in existing if q.get("is_real_exam"))
    non_exam_count = len(existing) - exam_count
    print(f"其中真题: {exam_count} 道，练习题: {non_exam_count} 道")
    
    # 按科目统计
    subjects = {}
    for q in existing:
        s = q.get("subject", "未知")
        subjects[s] = subjects.get(s, 0) + 1
    print("\n按科目统计:")
    for s, c in sorted(subjects.items()):
        print(f"  {s}: {c} 道")

if __name__ == "__main__":
    merge_exam_questions()

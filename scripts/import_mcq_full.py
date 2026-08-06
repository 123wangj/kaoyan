"""
从四个"含答案与解析"的PDF中提取题目、选项、答案、解析
使用基于【答案】标记的反向查找策略，可靠地提取所有题目
"""
import pdfplumber
import json
import re
from pathlib import Path

PDF_CONFIG = {
    "2025王道数据结构选择题_含答案与解析.pdf": {
        "subject": "数据结构",
        "source": "25王道数据结构选择题",
    },
    "2025王道操作系统选择题 _含答案与解析.pdf": {
        "subject": "操作系统",
        "source": "25王道操作系统选择题",
    },
    "2025王道计算机组成原理选择题_含答案与解析.pdf": {
        "subject": "计算机组成原理",
        "source": "25王道计组选择题",
    },
    "2025王道计算机网络选择题  (1)_含答案与解析.pdf": {
        "subject": "计算机网络",
        "source": "25王道计网选择题",
    },
}


CHAPTER_NAMES = {
    "数据结构": ["绪论", "线性表", "栈、队列和数组", "串", "树与二叉树", "图", "查找", "排序"],
    "操作系统": ["计算机系统概述", "进程与线程", "内存管理", "文件管理", "输入/输出(I/O)管理"],
    "计算机组成原理": ["计算机系统概述", "数据的表示和运算", "存储系统", "指令系统", "中央处理器(CPU)", "总线", "输入/输出系统"],
    "计算机网络": ["计算机网络体系结构", "物理层", "数据链路层", "网络层", "传输层", "应用层"],
}


def is_noise_line(line):
    s = line.strip()
    if not s:
        return True
    if re.search(r'第\s*\d+\s*页[，,]\s*共\s*\d+\s*页', s):
        return True
    if re.search(r'\d{2,4}-WD|WD-.*做题本|做题本.*第\d+章', s):
        return True
    if re.match(r'^-{4,}$', s):
        return True
    if s in ['目 录', '目录', '闲鱼:做题本集结地']:
        return True
    if re.match(r'^第\s*\d+\s*页$', s):
        return True
    if s in ['处理统计', '共提取题目:', '已作答:', '未确定:']:
        return True
    return False


def find_chapter_in_line(line):
    """在行中查找章节标题，返回 (chapter_number, chapter_name) 或 None"""
    m = re.search(r'第\s*(\d+)\s*章\s*(.+?)(?:\s*$)', line)
    if m:
        return int(m.group(1)), m.group(2).strip()
    return None


def find_section_in_line(line, subject):
    """在行中查找小节标题，返回 (chapter_number, section_text) 或 None"""
    m = re.search(r'▎?第\s*(\d+)\.(\d+)\s*节', line)
    if m:
        ch_num = int(m.group(1))
        sec_num = int(m.group(2))
        # 章节号应该在合理范围内（1-20）
        if ch_num > 20 or sec_num > 20:
            return None
        ch_names = CHAPTER_NAMES.get(subject, [])
        return ch_num, f"第{ch_num}.{sec_num}节"
    return None


def is_chapter_header(line):
    return bool(re.match(r'^第\s*\d+\s*章\s+', line.strip()))


def is_section_header(line):
    """检测小节标题，如 'X.Y 标题文字'，但排除IP地址等"""
    s = line.strip()
    # 必须包含中文字符
    if not re.search(r'[\u4e00-\u9fff]', s):
        return False
    # 数字.数字 后跟中文字符（避免IP地址）
    if re.match(r'^\d+\.\d+\s*[\u4e00-\u9fff]', s) and len(s) < 80:
        return True
    return False


def split_question_and_options(text):
    """将'题干 A. xxx B. xxx C. xxx D. xxx'拆分为题目和选项"""
    opt_pattern = re.compile(r'\s+([A-D])[\.\．\、\s]\s*')
    matches = list(opt_pattern.finditer(text))
    
    if not matches:
        return text, []
    
    first_opt = matches[0]
    before = text[:first_opt.start()]
    if len(before.strip()) < 3:
        return text, []
    
    question = text[:first_opt.start()].strip()
    options_text = text[first_opt.start():].strip()
    
    options = []
    opt_parts = opt_pattern.split(' ' + options_text)
    i = 1
    while i < len(opt_parts):
        if opt_parts[i] in 'ABCD':
            label = opt_parts[i]
            content = opt_parts[i+1].strip() if i+1 < len(opt_parts) else ''
            content = re.sub(r'\s+', ' ', content)
            options.append(f"{label}. {content}")
            i += 2
        else:
            i += 1
    
    question = re.sub(r'\s+', ' ', question)
    
    return question, options


def extract_from_page(lines, subject):
    """从一页的文本行中提取题目"""
    questions = []
    current_chapter = ""
    current_section = ""
    
    # Step 1: 找到所有【答案】位置
    answer_positions = []
    for i, line in enumerate(lines):
        if not is_noise_line(line):
            ans_match = re.match(r'【答案】\s*([A-D])', line)
            if ans_match:
                answer_positions.append((i, ans_match.group(1)))
    
    if not answer_positions:
        return questions, current_chapter, current_section
    
    # Step 2: 检测章节和小节
    ch_names = CHAPTER_NAMES.get(subject, [])
    for line in lines:
        # 先检测章节标题（行首的）
        if is_chapter_header(line):
            current_chapter = line
        # 检测行内章节标题（如 "第 2 章 进程与线程" 出现在行尾）
        ch_info = find_chapter_in_line(line)
        if ch_info:
            ch_num, ch_name = ch_info
            if ch_num <= len(ch_names):
                current_chapter = f"第{ch_num}章 {ch_names[ch_num-1]}"
            else:
                current_chapter = f"第{ch_num}章 {ch_name}"
        # 检测小节标题
        sec_info = find_section_in_line(line, subject)
        if sec_info:
            ch_num, sec_text = sec_info
            current_section = sec_text
            # 同时更新章节
            if ch_num <= len(ch_names):
                current_chapter = f"第{ch_num}章 {ch_names[ch_num-1]}"
        elif is_section_header(line):
            current_section = line
    
    # Step 3: 对每个【答案】，反向查找对应题目
    for ans_idx, answer in answer_positions:
        # 反向查找题目起始行
        q_start_idx = None
        q_number = ""
        
        for j in range(ans_idx - 1, max(ans_idx - 30, -1), -1):
            prev_line = lines[j].strip()
            if is_noise_line(prev_line):
                continue
            
            q_match = re.match(r'^(\d{1,3})[\.\．\、\s]+(.+)', prev_line)
            if q_match:
                q_num = q_match.group(1)
                q_text = q_match.group(2)
                
                # 排除选项行（A./B./C./D.开头）
                if re.match(r'^[A-D][\.\．\、\s]', q_text):
                    continue
                
                # 排除误判（如"2. **非线性结构**"这种解释中的编号）
                # 检查这一行或后续行中是否有选项
                has_options_nearby = False
                for k in range(j, ans_idx):
                    kl = lines[k].strip()
                    # 检查同行或后续行中是否有选项
                    if re.search(r'[A-D][\.\．\、\s]\s*\S', kl):
                        has_options_nearby = True
                        break
                
                if has_options_nearby:
                    q_start_idx = j
                    q_number = q_num
                    break
    
        if q_start_idx is None:
            continue
        
        # Step 4: 收集题目+选项的完整文本（从q_start_idx到ans_idx）
        q_text_parts = []
        for j in range(q_start_idx, ans_idx):
            l = lines[j].strip()
            if is_noise_line(l):
                continue
            # 移除题目编号
            if j == q_start_idx:
                q_match = re.match(r'^\d{1,3}[\.\．\、\s]+(.+)', l)
                if q_match:
                    l = q_match.group(1)
            q_text_parts.append(l)
        
        full_text = ' '.join(q_text_parts).strip()
        full_text = re.sub(r'\s+', ' ', full_text)
        
        # Step 5: 拆分题目和选项
        question_content, options = split_question_and_options(full_text)
        
        if not question_content or len(options) < 2:
            continue
        
        if len(options) > 4:
            options = options[:4]
        
        # Step 6: 提取解析
        explanation = ""
        exp_start = None
        for j in range(ans_idx + 1, min(ans_idx + 50, len(lines))):
            l = lines[j].strip()
            if is_noise_line(l):
                continue
            
            if re.match(r'【解析】', l):
                exp_match = re.match(r'【解析】\s*(.*)', l)
                exp_start = j
                if exp_match and exp_match.group(1).strip():
                    explanation = exp_match.group(1).strip()
                break
        
        if exp_start is not None:
            for j in range(exp_start + 1, min(exp_start + 50, len(lines))):
                l = lines[j].strip()
                if is_noise_line(l):
                    continue
                if re.match(r'【答案】', l):
                    break
                if re.match(r'^(\d{1,3})[\.\．\、\s]', l) and not re.match(r'^[A-D][\.\．\、\s]', l):
                    break
                if is_chapter_header(l) or is_section_header(l):
                    break
                explanation += ' ' + l
        
        explanation = re.sub(r'\s+', ' ', explanation).strip()
        
        is_real = '统考真题' in question_content
        
        questions.append({
            "type": "choice",
            "content": question_content,
            "options": options,
            "answer": answer,
            "explanation": explanation,
            "subject": subject,
            "chapter": current_chapter,
            "section": current_section,
            "knowledge_points": [],
            "difficulty": "中等" if is_real else "基础",
            "source": "",
            "is_real_exam": is_real,
            "question_number": q_number,
        })
    
    return questions, current_chapter, current_section


def parse_mcq_pdf(pdf_path, config):
    subject = config["subject"]
    source = config["source"]
    
    pdf = pdfplumber.open(pdf_path)
    all_questions = []
    current_chapter = ""
    current_section = ""
    
    for page_num, page in enumerate(pdf.pages):
        text = page.extract_text()
        if not text:
            continue
        
        lines = [l for l in text.split('\n') if l.strip()]
        
        questions, ch, sec = extract_from_page(lines, subject)
        if ch:
            current_chapter = ch
        if sec:
            current_section = sec
        
        for q in questions:
            q["chapter"] = current_chapter
            q["section"] = current_section
            q["source"] = source
            q["id"] = f"wd-mcq-{subject[:3]}-{page_num+1:03d}-{q['question_number']}"
            all_questions.append(q)
    
    pdf.close()
    return all_questions


def main():
    base_dir = Path(r"c:\Users\wang\Desktop\考研学习")
    tiku_dir = base_dir / "tiku"
    output_path = base_dir / "data" / "question_bank_new.jsonl"
    
    all_questions = []
    
    for filename, config in PDF_CONFIG.items():
        pdf_path = tiku_dir / filename
        if not pdf_path.exists():
            print(f"[SKIP] {filename} - not found")
            continue
        
        print(f"[PARSING] {filename} ({config['subject']})...")
        questions = parse_mcq_pdf(str(pdf_path), config)
        answered = sum(1 for q in questions if q['answer'])
        print(f"  -> {len(questions)} questions, {answered} with answers")
        all_questions.extend(questions)
    
    with open(output_path, "w", encoding="utf-8") as f:
        for q in all_questions:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    
    total = len(all_questions)
    answered = sum(1 for q in all_questions if q['answer'])
    print(f"\n=== Summary ===")
    print(f"Total: {total} questions, {answered} with answers ({100*answered//max(total,1)}%)")
    for s in sorted(set(q["subject"] for q in all_questions)):
        c = sum(1 for q in all_questions if q["subject"] == s)
        a = sum(1 for q in all_questions if q["subject"] == s and q['answer'])
        exp = sum(1 for q in all_questions if q["subject"] == s and q['explanation'])
        print(f"  {s}: {c} questions, {a} with answers, {exp} with explanations")
    print(f"\nOutput: {output_path}")


if __name__ == "__main__":
    main()
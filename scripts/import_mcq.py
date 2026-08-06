"""
Phase 1: 从 MCQ（选择题）PDF 中提取题目和选项
支持两种格式：
  - 格式A: "1. 题干" （数据结构/OS/计组）
  - 格式B: "1 题干"   （计网）
"""

import pdfplumber
import json
import re
from pathlib import Path

PDF_CONFIG = {
    "2025王道数据结构选择题.pdf": {
        "subject": "数据结构",
        "source": "25王道数据结构选择题",
    },
    "2025王道操作系统选择题 .pdf": {
        "subject": "操作系统",
        "source": "25王道操作系统选择题",
    },
    "2025王道计算机组成原理选择题.pdf": {
        "subject": "计算机组成原理",
        "source": "25王道计组选择题",
    },
    "2025王道计算机网络选择题  (1).pdf": {
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
    """判断是否为噪声行（页眉、页脚、分隔线等）"""
    if not line or not line.strip():
        return True
    s = line.strip()
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
    if re.match(r'^\d+\.\d+\s+\d+$', s):  # page numbers like "1.1 3"
        return True
    return False


def is_question_start(line):
    """判断是否为题目起始行：数字开头 + 空格或点号"""
    return bool(re.match(r'^(\d+)[\.\．\、\s]\s*(?=\S)', line.strip()))


def is_option_line(line):
    """判断是否为选项行：A/B/C/D 开头"""
    return bool(re.match(r'^([A-D])[\.\．\、\s]', line.strip()))


def is_chapter_header(line):
    """检测章节标题"""
    return bool(re.match(r'^第\s*\d+\s*章\s+', line.strip()))


def is_section_header(line):
    """检测小节标题，如 1.1 xxx"""
    s = line.strip()
    if re.match(r'^\d+\.\d+\s+\S', s) and len(s) < 80:
        return True
    return False


def cleanup_option_text(text):
    """清理选项文本，移除可能混入的下一个题目碎片"""
    m = re.search(r'\d+[\.\．]\s*【?\d{4}\s*统考真题】?', text)
    if m:
        text = text[:m.start()].strip()
    return text


def split_merged_options(current_label, text):
    """拆分同一行中合并的选项，如 'A. 程序 B. 问题求解步骤的描述' -> ['A. 程序', 'B. 问题求解步骤的描述']"""
    results = []
    
    # 在文本中查找所有选项标记 B. C. D.
    pattern = re.compile(r'(?<!\d)([B-D])[\.\．\、]\s*')
    matches = list(pattern.finditer(text))
    
    if not matches:
        results.append(f"{current_label}. {text}")
        return results
    
    # 按匹配位置拆分
    last_end = 0
    for m in matches:
        part = text[last_end:m.start()].strip()
        if part:
            results.append(f"{current_label}. {part}")
        current_label = m.group(1)
        last_end = m.end()
    
    # 最后一段
    remaining = text[last_end:].strip()
    if remaining:
        results.append(f"{current_label}. {remaining}")
    
    return results if results else [f"{current_label}. {text}"]


def extract_questions(text_lines, subject):
    """从文本行列表中提取题目"""
    questions = []
    current_chapter = ""
    current_section = ""
    
    i = 0
    while i < len(text_lines):
        line = text_lines[i].strip()
        
        if is_noise_line(line):
            i += 1
            continue
        
        # 检测章节
        if is_chapter_header(line):
            current_chapter = line
            i += 1
            continue
        
        if is_section_header(line):
            current_section = line
            i += 1
            continue
        
        # 检测题目开始
        if is_question_start(line) and not is_option_line(line):
            q_match = re.match(r'^(\d+)[\.\．\、\s]+(.+)', line)
            if not q_match:
                i += 1
                continue
            
            q_num = q_match.group(1)
            q_text = q_match.group(2).strip()
            
            # 收集跨行的题目正文
            i += 1
            q_lines = [q_text]
            while i < len(text_lines):
                nl = text_lines[i].strip()
                if is_noise_line(nl):
                    i += 1
                    continue
                if is_option_line(nl) or is_question_start(nl):
                    break
                if is_chapter_header(nl) or is_section_header(nl):
                    break
                q_lines.append(nl)
                i += 1
            
            q_full = ' '.join(q_lines).strip()
            q_full = re.sub(r'\s+', ' ', q_full)
            
            # 收集选项
            raw_options = []
            while i < len(text_lines):
                ol = text_lines[i].strip()
                if is_noise_line(ol):
                    i += 1
                    continue
                if is_question_start(ol) and not is_option_line(ol):
                    break
                if is_chapter_header(ol):
                    break
                
                opt_match = re.match(r'^([A-D])[\.\．\、\s]+(.+)', ol)
                if opt_match:
                    label = opt_match.group(1)
                    opt_text = opt_match.group(2).strip()
                    i += 1
                    
                    # 收集跨行选项
                    while i < len(text_lines):
                        nl = text_lines[i].strip()
                        if is_noise_line(nl):
                            i += 1
                            continue
                        if is_option_line(nl) or is_question_start(nl):
                            break
                        if is_chapter_header(nl):
                            break
                        opt_text += ' ' + nl
                        i += 1
                    
                    opt_text = re.sub(r'\s+', ' ', opt_text).strip()
                    raw_options.append((label, opt_text))
                else:
                    break
            
            # 拆分同行的合并选项 (A. xxx B. xxx -> 独立 A 和 B)
            options = []
            seen_labels = set()
            for label, text in raw_options:
                text = cleanup_option_text(text)
                parts = split_merged_options(label, text)
                for p in parts:
                    cleaned = cleanup_option_text(p)
                    # 提取标签去重
                    opt_label = cleaned[0] if cleaned and cleaned[0] in 'ABCD' else ''
                    if opt_label not in seen_labels and cleaned:
                        seen_labels.add(opt_label)
                        options.append(cleaned)
            
            # 过滤：只保留4个及以内的选项，且至少2个
            if len(options) > 4:
                options = options[:4]
            
            if q_full and len(options) >= 2:
                is_real = '统考真题' in q_full
                questions.append({
                    "type": "choice",
                    "content": q_full,
                    "options": options,
                    "answer": "",
                    "explanation": "",
                    "subject": subject,
                    "chapter": current_chapter,
                    "section": current_section,
                    "knowledge_points": [],
                    "difficulty": "中等" if is_real else "基础",
                    "source": "",
                    "is_real_exam": is_real,
                    "question_number": q_num,
                })
            continue
        
        i += 1
    
    return questions, current_chapter, current_section


def parse_mcq_pdf(pdf_path, config):
    """解析一本选择题PDF"""
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
        
        questions, ch, sec = extract_questions(lines, subject)
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
    output_path = base_dir / "data" / "question_bank_mcq.jsonl"
    
    all_questions = []
    
    for filename, config in PDF_CONFIG.items():
        pdf_path = tiku_dir / filename
        if not pdf_path.exists():
            print(f"[SKIP] {filename}")
            continue
        
        print(f"[PARSING] {filename} ({config['subject']})...")
        questions = parse_mcq_pdf(str(pdf_path), config)
        print(f"  -> {len(questions)} 道")
        all_questions.extend(questions)
    
    with open(output_path, "w", encoding="utf-8") as f:
        for q in all_questions:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    
    print(f"\n总计: {len(all_questions)} 道")
    for s in sorted(set(q["subject"] for q in all_questions)):
        c = sum(1 for q in all_questions if q["subject"] == s)
        print(f"  {s}: {c} 道")
    print(f"输出: {output_path}")


if __name__ == "__main__":
    main()
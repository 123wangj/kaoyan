"""
Phase 2 v2: OCR 处理图片型 PDF - 优化版
- 跳过 ToC/目录页
- 清洗水印/页眉页脚
- 更好的题目边界检测
- 将大题和知识点分别入库
"""

import fitz
import easyocr
import json
import re
import time
import os
from pathlib import Path
import hashlib

BASE_DIR = Path(r"c:\Users\wang\Desktop\考研学习")
TIKU_DIR = BASE_DIR / "tiku"
DATA_DIR = BASE_DIR / "data"

IMAGE_PDFS = [
    {"filename": "25王道《数据结构》大题.pdf", "subject": "数据结构", "type": "big_question", "source": "25王道数据结构大题"},
    {"filename": "25王道《操作系统》大题.pdf", "subject": "操作系统", "type": "big_question", "source": "25王道操作系统大题"},
    {"filename": "25王道《计组》大题.pdf", "subject": "计算机组成原理", "type": "big_question", "source": "25王道计组大题"},
    {"filename": "25王道《计网》大题.pdf", "subject": "计算机网络", "type": "big_question", "source": "25王道计网大题"},
    {"filename": "数据结构（总笔记）163Pq.pdf", "subject": "数据结构", "type": "knowledge", "source": "数据结构总笔记"},
    {"filename": "操作系统（总笔记）159Pq.pdf", "subject": "操作系统", "type": "knowledge", "source": "操作系统总笔记"},
    {"filename": "组成原理（总笔记）156Pq.pdf", "subject": "计算机组成原理", "type": "knowledge", "source": "计组总笔记"},
    {"filename": "计网（总笔记）101Pq.pdf", "subject": "计算机网络", "type": "knowledge", "source": "计网总笔记"},
    {"filename": "【灰灰考研】94页计算机初试必背名词解释+简答题汇总-.pdf", "subject": "综合", "type": "knowledge", "source": "灰灰考研名词解释"},
]

NOISE_PATTERNS = [
    r'微信[公众号]*[：:]\s*研[七\d]+',
    r'微信公众号\S*',
    r'王[道茬][考研]*\s*[A-Z]*',
    r'灰灰考研',
    r'^\s*\d+\s*$',
    r'^\s*[IVX]+\s*$',
    r'^\s*P\d+\s*$',
]


def clean_text(text):
    for pat in NOISE_PATTERNS:
        text = re.sub(pat, '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def is_toc_page(ocr_text):
    chapter_count = len(re.findall(r'第[一二三四五六七八九十\d]+章', ocr_text))
    section_count = len(re.findall(r'\d+\.\d+\s', ocr_text))
    lines = [l.strip() for l in ocr_text.split('\n') if l.strip()]
    if len(lines) == 0:
        return False
    short_lines = sum(1 for l in lines if len(l) < 40)
    if len(lines) >= 8 and short_lines / len(lines) > 0.8 and chapter_count >= 3:
        return True
    if chapter_count >= 5 and short_lines / max(len(lines), 1) > 0.6:
        return True
    return False


def is_blank_page(ocr_text):
    text = ocr_text.strip()
    if len(text) < 10:
        return True
    meaningful = re.sub(r'[\s\d.,:;()（）\[\]【】\-_/\\]+', '', text)
    if len(meaningful) < 5:
        return True
    return False


def parse_big_questions(ocr_text, subject, source, page_num):
    questions = []
    text = clean_text(ocr_text)
    
    pos = 0
    q_count = 0
    
    while pos < len(text):
        m = re.search(r'(\d{1,2})[\.\．\、\s]+(?!\d)', text[pos:])
        if not m:
            remaining = text[pos:].strip()
            if len(remaining) > 30:
                q_count += 1
                q_id = f"ocr-bq-{subject[:3]}-{page_num+1:03d}-{q_count}"
                questions.append({
                    "type": "big_question", "content": remaining, "answer": "",
                    "explanation": "", "subject": subject, "chapter": "",
                    "section": "", "knowledge_points": [], "difficulty": "中等",
                    "source": source, "id": q_id,
                })
            break
        
        q_num = m.group(1)
        start = pos + m.start()
        pos = pos + m.end()
        
        m2 = re.search(r'\d{1,2}[\.\．\、\s]+(?!\d)', text[pos:])
        if m2:
            q_body = text[start:pos + m2.start()].strip()
            next_start = pos + m2.start()
        else:
            q_body = text[start:].strip()
            next_start = len(text)
        
        q_body_clean = q_body.strip()
        
        if len(q_body_clean) > 15:
            q_count += 1
            q_id = f"ocr-bq-{subject[:3]}-{page_num+1:03d}-{q_count}"
            questions.append({
                "type": "big_question", "content": q_body_clean, "answer": "",
                "explanation": "", "subject": subject, "chapter": "",
                "section": "", "knowledge_points": [], "difficulty": "中等",
                "source": source, "id": q_id,
            })
        
        pos = next_start
    
    return questions


def parse_knowledge_chunks(ocr_text, subject, source, page_num):
    chunks = []
    text = clean_text(ocr_text)
    
    paras = re.split(r'\n\s*\n|\n(?=[A-Z\*\#\（\(【\[])|(?<=\。)\s*\n', text)
    
    for para in paras:
        para = para.strip()
        if len(para) < 15:
            continue
        if len(para) > 5000:
            subparas = re.split(r'(?<=\。)\s*(?=[A-Z\u4e00-\u9fff])', para)
            for sp in subparas:
                sp = sp.strip()
                if len(sp) < 15:
                    continue
                title = sp.split('。')[0][:80] if '。' in sp else sp[:80]
                chunk_id = hashlib.md5(f"{source}-{page_num}-{len(chunks)}".encode()).hexdigest()[:12]
                chunks.append({
                    "id": f"ocr-kp-{chunk_id}", "title": title, "content": sp,
                    "subject": subject, "chapter": "", "section": "",
                    "knowledge_points": [], "difficulty": "基础",
                    "source": source, "score_points": [],
                })
            continue
        
        title = para.split('。')[0][:80] if '。' in para else para[:80]
        chunk_id = hashlib.md5(f"{source}-{page_num}-{len(chunks)}".encode()).hexdigest()[:12]
        chunks.append({
            "id": f"ocr-kp-{chunk_id}", "title": title, "content": para,
            "subject": subject, "chapter": "", "section": "",
            "knowledge_points": [], "difficulty": "基础",
            "source": source, "score_points": [],
        })
    
    return chunks


class Pipeline:
    def __init__(self):
        self.progress_file = DATA_DIR / "ocr_progress.json"
        self.progress = self._load_progress()
        self.reader = None
    
    def _load_progress(self):
        if self.progress_file.exists():
            return json.loads(self.progress_file.read_text(encoding='utf-8'))
        return {}
    
    def _save_progress(self):
        self.progress_file.write_text(json.dumps(self.progress, ensure_ascii=False), encoding='utf-8')
    
    def run(self, max_pages=None):
        self.reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
        
        total_bq = 0
        total_kp = 0
        
        for config in IMAGE_PDFS:
            filename = config["filename"]
            subject = config["subject"]
            ptype = config["type"]
            source = config["source"]
            
            pdf_path = TIKU_DIR / filename
            if not pdf_path.exists():
                print(f"  [SKIP] {filename}")
                continue
            
            doc = fitz.open(str(pdf_path))
            total = len(doc)
            pages = min(total, max_pages) if max_pages else total
            
            key = f"{filename}:{ptype}"
            done = set(self.progress.get(key, []))
            
            bq_list = []
            kp_list = []
            
            skipped_toc = 0
            skipped_blank = 0
            
            for pn in range(pages):
                if pn in done:
                    continue
                
                try:
                    page = doc[pn]
                    pix = page.get_pixmap(dpi=150)
                    img_bytes = pix.tobytes("png")
                    results = self.reader.readtext(img_bytes, detail=1)
                    ocr_text = "\n".join([r[1] for r in results if r[2] > 0.3])
                    
                    if is_blank_page(ocr_text):
                        skipped_blank += 1
                        done.add(pn)
                        continue
                    
                    if ptype == "big_question" and is_toc_page(ocr_text):
                        skipped_toc += 1
                        done.add(pn)
                        continue
                    
                    if ptype == "big_question":
                        qs = parse_big_questions(ocr_text, subject, source, pn)
                        bq_list.extend(qs)
                    else:
                        chunks = parse_knowledge_chunks(ocr_text, subject, source, pn)
                        kp_list.extend(chunks)
                    
                    done.add(pn)
                    
                except Exception as e:
                    print(f"  [ERR] {filename} p{pn+1}: {e}")
                    continue
            
            doc.close()
            
            self.progress[key] = sorted(done)
            self._save_progress()
            
            if bq_list:
                with open(DATA_DIR / "question_bank_big.jsonl", "a", encoding="utf-8") as f:
                    for q in bq_list:
                        f.write(json.dumps(q, ensure_ascii=False) + "\n")
            
            if kp_list:
                with open(DATA_DIR / "knowledge_points_ocr.jsonl", "a", encoding="utf-8") as f:
                    for k in kp_list:
                        f.write(json.dumps(k, ensure_ascii=False) + "\n")
            
            print(f"  {filename}: {len(bq_list)}Q {len(kp_list)}KP (toc:{skipped_toc} blank:{skipped_blank})")
            total_bq += len(bq_list)
            total_kp += len(kp_list)
        
        print(f"\nTotal: {total_bq} big questions, {total_kp} knowledge chunks")


if __name__ == "__main__":
    import sys
    mp = int(sys.argv[1]) if len(sys.argv) > 1 else None
    p = Pipeline()
    p.run(max_pages=mp)
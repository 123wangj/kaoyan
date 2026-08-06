"""
Phase 2 Final: 增量 OCR 批处理 - 后台运行，断点续传
python scripts/ocr_batch.py
"""

import fitz
import easyocr
import json
import re
import time
import hashlib
from pathlib import Path
import sys
import io

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

BASE = Path(r"c:\Users\wang\Desktop\考研学习")
TIKU = BASE / "tiku"
DATA = BASE / "data"

JOBS = [
    {"file": "25王道《数据结构》大题.pdf", "subj": "数据结构", "kind": "big"},
    {"file": "25王道《操作系统》大题.pdf", "subj": "操作系统", "kind": "big"},
    {"file": "25王道《计组》大题.pdf",     "subj": "计算机组成原理", "kind": "big"},
    {"file": "25王道《计网》大题.pdf",     "subj": "计算机网络", "kind": "big"},
    {"file": "数据结构（总笔记）163Pq.pdf","subj": "数据结构", "kind": "kp"},
    {"file": "操作系统（总笔记）159Pq.pdf","subj": "操作系统", "kind": "kp"},
    {"file": "组成原理（总笔记）156Pq.pdf","subj": "计算机组成原理", "kind": "kp"},
    {"file": "计网（总笔记）101Pq.pdf",    "subj": "计算机网络", "kind": "kp"},
    {"file": "【灰灰考研】94页计算机初试必背名词解释+简答题汇总-.pdf","subj":"综合","kind":"kp"},
]

PROGRESS_FILE = DATA / "ocr_progress.json"
BQ_FILE = DATA / "question_bank_big.jsonl"
KP_FILE = DATA / "knowledge_points_ocr.jsonl"

NOISE = [
    r'微信[公众号]*[：:]\s*研[七\d]+',
    r'微信公众号\S*',
    r'王[道茬][考研]*\s*[A-Z]*',
    r'灰灰考研',
    r'徵信公众号[：:]\s*\S*',
    r'^\s*[IVX]+\s*$',
    r'^\s*P\d+\s*$',
    r'壬道',
]

def clean(text):
    for p in NOISE:
        text = re.sub(p, '', text)
    return re.sub(r'\s+', ' ', text).strip()

def is_toc(text):
    ch = len(re.findall(r'第[一二三四五六七八九十\d]+章', text))
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if not lines:
        return False
    short = sum(1 for l in lines if len(l) < 40)
    if ch >= 5 and short / len(lines) > 0.6:
        return True
    if len(lines) >= 6 and short / len(lines) > 0.75 and ch >= 2:
        return True
    if re.search(r'目\s*录', text) and short / len(lines) > 0.7:
        return True
    return False

def is_cover(text):
    t = text.strip()
    if re.search(r'(考研计算机|综合题做题本|王道.*综合题)', t) and len(t) < 80:
        return True
    return False

def is_blank(text):
    t = text.strip()
    if len(t) < 10:
        return True
    m = re.sub(r'[\s\d.,:;()（）\[\]【】\-_/\\]+', '', t)
    return len(m) < 5

def split_questions(text, subj, source, pn):
    qs = []
    text = clean(text)
    pos = 0
    cnt = 0
    while pos < len(text):
        m = re.search(r'(\d{1,2})[\.\．\、\s]+(?!\d)', text[pos:])
        if not m:
            rest = text[pos:].strip()
            if len(rest) > 30 and not is_toc(rest) and not is_cover(rest):
                cnt += 1
                qs.append({
                    "type":"big_question","content":rest,"answer":"","explanation":"",
                    "subject":subj,"chapter":"","section":"","knowledge_points":[],
                    "difficulty":"中等","source":source,
                    "id":f"ocr-bq-{subj[:3]}-{pn+1:03d}-{cnt}"
                })
            break
        start = pos + m.start()
        pos = pos + m.end()
        m2 = re.search(r'\d{1,2}[\.\．\、\s]+(?!\d)', text[pos:])
        if m2:
            body = text[start:pos + m2.start()].strip()
            pos = pos + m2.start()
        else:
            body = text[start:].strip()
            pos = len(text)
        if len(body) > 15:
            cnt += 1
            qs.append({
                "type":"big_question","content":body,"answer":"","explanation":"",
                "subject":subj,"chapter":"","section":"","knowledge_points":[],
                "difficulty":"中等","source":source,
                "id":f"ocr-bq-{subj[:3]}-{pn+1:03d}-{cnt}"
            })
    return qs

def split_knowledge(text, subj, source, pn):
    chunks = []
    text = clean(text)
    paras = re.split(r'\n\s*\n', text)
    for pa in paras:
        pa = pa.strip()
        if len(pa) < 15:
            continue
        if len(pa) > 3000:
            for sp in re.split(r'(?<=\。)\s*(?=[A-Z\u4e00-\u9fff])', pa):
                sp = sp.strip()
                if len(sp) < 15:
                    continue
                hid = hashlib.md5(f"{source}-{pn}-{len(chunks)}".encode()).hexdigest()[:10]
                chunks.append({
                    "id":f"ocr-kp-{hid}","title":sp[:80],"content":sp,
                    "subject":subj,"chapter":"","section":"","knowledge_points":[],
                    "difficulty":"基础","source":source,"score_points":[]
                })
            continue
        hid = hashlib.md5(f"{source}-{pn}-{len(chunks)}".encode()).hexdigest()[:10]
        chunks.append({
            "id":f"ocr-kp-{hid}","title":pa[:80],"content":pa,
            "subject":subj,"chapter":"","section":"","knowledge_points":[],
            "difficulty":"基础","source":source,"score_points":[]
        })
    return chunks

def load_prog():
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text(encoding='utf-8'))
    return {}

def save_prog(p):
    PROGRESS_FILE.write_text(json.dumps(p, ensure_ascii=False), encoding='utf-8')

def main():
    prog = load_prog()
    gpu_avail = False
    try:
        import torch; gpu_avail = torch.cuda.is_available()
    except: pass
    reader = easyocr.Reader(['ch_sim', 'en'], gpu=gpu_avail)
    print(f"[GPU] {'Enabled' if gpu_avail else 'Disabled (CPU mode)'}")
    
    for job in JOBS:
        fname = job["file"]
        subj = job["subj"]
        kind = job["kind"]
        src = fname.replace(".pdf","")
        
        path = TIKU / fname
        if not path.exists():
            print(f"[SKIP] {fname}")
            continue
        
        doc = fitz.open(str(path))
        total = len(doc)
        key = fname
        done = set(prog.get(key, []))
        
        bqs = []
        kps = []
        skip_toc = 0
        skip_cover = 0
        skip_blank = 0
        
        print(f"\n[{kind.upper()}] {fname} ({total}p, {len(done)} done)")
        t0 = time.time()
        
        for pn in range(total):
            if pn in done:
                continue
            
            try:
                page = doc[pn]
                pix = page.get_pixmap(dpi=150)
                img = pix.tobytes("png")
                res = reader.readtext(img, detail=1)
                txt = "\n".join([r[1] for r in res if r[2] > 0.3])
                
                if is_blank(txt):
                    skip_blank += 1
                    done.add(pn)
                elif kind == "big" and is_toc(txt):
                    skip_toc += 1
                    done.add(pn)
                elif kind == "big" and is_cover(txt):
                    skip_cover += 1
                    done.add(pn)
                elif kind == "big":
                    qs = split_questions(txt, subj, src, pn)
                    bqs.extend(qs)
                    done.add(pn)
                else:
                    chunks = split_knowledge(txt, subj, src, pn)
                    kps.extend(chunks)
                    done.add(pn)
                
                prog[key] = sorted(done)
                
                if (pn + 1) % 10 == 0:
                    if bqs:
                        with open(BQ_FILE, "a", encoding="utf-8") as f:
                            for q in bqs:
                                f.write(json.dumps(q, ensure_ascii=False) + "\n")
                    if kps:
                        with open(KP_FILE, "a", encoding="utf-8") as f:
                            for k in kps:
                                f.write(json.dumps(k, ensure_ascii=False) + "\n")
                    bqs, kps = [], []
                    save_prog(prog)
                    elapsed = time.time() - t0
                    print(f"  ... p{pn+1}/{total} ({elapsed:.0f}s, saved)")
                    
            except Exception as e:
                print(f"  [ERR] p{pn+1}: {e}")
                done.add(pn)
        
        doc.close()
        save_prog(prog)
        
        if bqs:
            with open(BQ_FILE, "a", encoding="utf-8") as f:
                for q in bqs:
                    f.write(json.dumps(q, ensure_ascii=False) + "\n")
        if kps:
            with open(KP_FILE, "a", encoding="utf-8") as f:
                for k in kps:
                    f.write(json.dumps(k, ensure_ascii=False) + "\n")
        
        elapsed = time.time() - t0
        print(f"  DONE: {len(bqs)}Q {len(kps)}KP (toc:{skip_toc} cover:{skip_cover} blank:{skip_blank}) in {elapsed:.0f}s")
    
    print(f"\n{'='*50}")
    print("ALL DONE. Output:")
    print(f"  {BQ_FILE}")
    print(f"  {KP_FILE}")

if __name__ == "__main__":
    main()
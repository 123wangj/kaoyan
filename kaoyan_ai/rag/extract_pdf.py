from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import fitz
from rapidocr_onnxruntime import RapidOCR

from kaoyan_ai.utils.jsonl import append_jsonl

PDF_DIR = Path(r"c:\Users\wang\Desktop\考研学习\wangdao")
DATA_DIR = Path(r"c:\Users\wang\Desktop\考研学习\data")

PDF_FILES = {
    "数据结构": PDF_DIR / "2027数据结构_高清带书签版.pdf",
    "计算机组成原理": PDF_DIR / "2027计算机组成原理_高清带书签版.pdf",
    "计算机网络": PDF_DIR / "2027计算机网络_高清带书签版.pdf",
    "操作系统": PDF_DIR / "操作系统.pdf",
}

QB_FILE = DATA_DIR / "question_bank.jsonl"
KP_FILE = DATA_DIR / "knowledge_points.jsonl"
PROGRESS_FILE = DATA_DIR / "extract_progress.json"

QQ = r"[\.\、\．\s]"


def norm(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def ocr_page(engine: RapidOCR, pix, page_num: int) -> str:
    try:
        result, _ = engine(pix.tobytes("png"))
        if result is None:
            return ""
        lines = [str(item[1]) for item in result]
        return "\n".join(lines)
    except Exception as exc:
        print(f"  [OCR error p{page_num}]: {exc}")
        return ""


def parse_questions(text: str) -> list[dict]:
    items = []
    mcq_blocks = re.split(rf"\n(?=\d{{2,3}}{QQ})", text)

    for block in mcq_blocks:
        block = norm(block)
        if not block:
            continue

        m = re.match(rf"(\d{{1,3}})\s*{QQ}+(.*)", block, re.DOTALL)
        if not m:
            continue
        q_num = m.group(1)
        rest = m.group(2)

        opts = re.findall(rf"\n?([A-D]){QQ}+(.*?)(?=\n?[A-D]{QQ}|\n?\d{{2,}}{QQ}|\Z)", rest, re.DOTALL)
        if len(opts) >= 2:
            q_content = norm(rest.split(f"\n{opts[0][0]}")[0]) if opts else norm(rest)
            options = [f"{l}. {norm(t)}" for l, t in opts]
            items.append({
                "type": "choice",
                "question_number": q_num,
                "content": q_content,
                "options": options,
                "answer": "",
                "explanation": "",
            })

    return items


def parse_answers(text: str) -> dict[str, dict]:
    results = {}

    sections = re.split(r"\n(?=[一二三四五六七八九十]、)", text)
    for section_text in sections:
        blocks = re.split(rf"\n(?=\d{{2,3}}{QQ})", section_text)
        for block in blocks:
            block = norm(block)
            m = re.match(rf"(\d{{1,3}})\s*{QQ}+", block)
            if not m:
                continue
            q_num = m.group(1)
            rest = block[m.end():]

            ans_m = re.search(rf"([A-D])\s*(?:\n|$)", rest[:20])
            if not ans_m:
                continue

            answer = ans_m.group(1)
            expl = norm(rest[ans_m.end():])
            expl = re.sub(r"^\s*[\.\、\．]+", "", expl)

            if q_num not in results:
                results[q_num] = {"answer": answer, "explanation": expl}

    return results


def extract_knowledge_points(text: str, subject: str, chapter: str, section: str, page: int) -> list[dict]:
    results = []
    text = norm(text)
    if len(text) < 40:
        return results

    paragraphs = re.split(r"\n{2,}", text)
    kp_idx = 0
    for para in paragraphs:
        para = norm(para)
        if len(para) < 80:
            continue
        title_line = para.split("\n")[0][:60]
        results.append({
            "id": f"kp-{subject}-{chapter}-{section}-p{page}-{kp_idx}",
            "title": title_line,
            "content": para[:1200],
            "subject": subject,
            "knowledge_points": [chapter, section],
            "difficulty": "基础",
            "source": f"王道{subject}教材 p{page}",
            "score_points": [],
        })
        kp_idx += 1
        if kp_idx >= 5:
            break

    return results


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    return {}


def save_progress(prog: dict) -> None:
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(prog, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_directory_toc(doc, total: int) -> tuple[dict[int, dict], dict[int, dict], dict[int, dict]]:
    engine = RapidOCR()
    question_starts: dict[int, dict] = {}
    answer_starts: dict[int, dict] = {}
    chapter_map: dict[int, dict] = {}

    toc_text = ""
    print("  OCR目录页...")
    for pn in range(8, 13):
        page = doc[pn - 1]
        pix = page.get_pixmap(dpi=150)
        toc_text += ocr_page(engine, pix, pn) + "\n"

    PAGE_OFFSET = 12

    lines = [l.strip() for l in toc_text.split("\n") if l.strip()]
    cur_chapter = ""

    for i, line in enumerate(lines):
        ch_match = re.match(r"第\s*(\d+)\s*章\s*(.*)", line)
        if ch_match:
            cur_chapter = line
            ch_num = int(ch_match.group(1))

            if ch_num == 1:
                book_page = 1
                pdf_page = book_page + PAGE_OFFSET
                if 1 <= pdf_page <= total and pdf_page not in chapter_map:
                    chapter_map[pdf_page] = {"chapter": cur_chapter}
            else:
                for j in range(i + 1, min(i + 15, len(lines))):
                    nxt = lines[j]
                    if re.match(r"第\s*\d+\s*章", nxt):
                        break
                    m = re.search(r"(\d+)\s*$", nxt)
                    if m:
                        book_page = int(m.group(1))
                        if 10 <= book_page <= total:
                            pdf_page = book_page + PAGE_OFFSET
                            if 1 <= pdf_page <= total and pdf_page not in chapter_map:
                                chapter_map[pdf_page] = {"chapter": cur_chapter}
                        break
            continue

        is_exercise = "习题精选" in line or "试题精选" in line
        is_answer = "答案与解析" in line or "答案和解析" in line

        if is_exercise or is_answer:
            m = re.search(r"(\d+)\s*$", line)
            if m:
                book_page = int(m.group(1))
            elif i + 1 < len(lines):
                nxt = lines[i + 1]
                m = re.search(r"[·\.]?\s*(\d+)\s*$", nxt)
                if m:
                    book_page = int(m.group(1))
                else:
                    continue
            else:
                continue

            if not (10 <= book_page <= total):
                continue

            pdf_page = book_page + PAGE_OFFSET
            if not (1 <= pdf_page <= total):
                continue

            if is_exercise:
                question_starts[pdf_page] = {"chapter": cur_chapter, "section": line, "title": line}
            else:
                answer_starts[pdf_page] = {"chapter": cur_chapter, "section": line, "title": line}

    print(f"  目录解析: 章节={len(chapter_map)}, 题目节={len(question_starts)}, 答案节={len(answer_starts)}")
    return question_starts, answer_starts, chapter_map


def process_pdf(pdf_path: Path, subject: str) -> dict:
    doc = fitz.open(str(pdf_path))
    total = doc.page_count
    toc = doc.get_toc()

    print(f"\n{'='*60}")
    print(f"[{subject}] {pdf_path.name}")
    print(f"总页: {total} | 目录条目: {len(toc)}")
    print(f"{'='*60}")

    prog = load_progress()
    key = pdf_path.name
    if key not in prog:
        prog[key] = {"done": [], "q_count": 0, "kp_count": 0, "matched": 0}

    question_starts: dict[int, dict] = {}
    answer_starts: dict[int, dict] = {}
    all_toc_pages: set[int] = set()
    chapter_map: dict[int, dict] = {}

    if toc:
        cur_chapter = ""
        cur_section = ""

        for item in toc:
            lvl, title, page = item[0], item[1], item[2]
            all_toc_pages.add(page)
            if lvl == 1 and re.search(r"第.*章", title):
                cur_chapter = title
            elif lvl == 2:
                cur_section = title
            elif lvl == 3:
                if re.search(r"试题精选|习题", title):
                    question_starts[page] = {"chapter": cur_chapter, "section": cur_section, "title": title}
                elif re.search(r"答案|解析", title):
                    answer_starts[page] = {"chapter": cur_chapter, "section": cur_section, "title": title}
    else:
        question_starts, answer_starts, chapter_map = _parse_directory_toc(doc, total)
        all_toc_pages = set(list(question_starts.keys()) + list(answer_starts.keys()) + list(chapter_map.keys()))

    sorted_toc_pages = sorted(all_toc_pages)

    def _expand_pages(start_page: int) -> list[int]:
        result = [start_page]
        for i in range(len(sorted_toc_pages)):
            if sorted_toc_pages[i] == start_page and i + 1 < len(sorted_toc_pages):
                next_boundary = sorted_toc_pages[i + 1]
                break
        else:
            next_boundary = total + 1
        for p in range(start_page + 1, next_boundary):
            if p <= total:
                result.append(p)
        return result

    question_page_set: set[int] = set()
    answer_page_set: set[int] = set()

    for qp in question_starts:
        for p in _expand_pages(qp):
            question_page_set.add(p)
    for ap in answer_starts:
        for p in _expand_pages(ap):
            answer_page_set.add(p)

    print(f"题目页: {len(question_starts)} 起始 (+{len(question_page_set) - len(question_starts)} 连续) | "
          f"答案页: {len(answer_starts)} 起始 (+{len(answer_page_set) - len(answer_starts)} 连续)")

    engine = RapidOCR()
    total_q = prog[key]["q_count"]
    total_kp = prog[key]["kp_count"]

    all_target_pages = sorted(question_page_set | answer_page_set)

    for pnum in all_target_pages:
        if pnum in prog[key]["done"]:
            continue
        if pnum < 1 or pnum > total:
            continue

        page = doc[pnum - 1]
        pix = page.get_pixmap(dpi=200)
        text = ocr_page(engine, pix, pnum)

        if not text:
            prog[key]["done"].append(pnum)
            continue

        is_question = pnum in question_page_set
        is_answer = pnum in answer_page_set

        if is_question:
            info = question_starts.get(pnum)
            if info is None:
                for qp in sorted(question_starts.keys()):
                    if qp <= pnum:
                        info = question_starts[qp]
            chapter = info.get("chapter", "") if info else ""
            section = info.get("section", "") if info else ""

            questions = parse_questions(text)
            for q in questions:
                q["subject"] = subject
                q["chapter"] = chapter
                q["section"] = section
                q["knowledge_points"] = []
                q["difficulty"] = "基础"
                q["source"] = f"王道{subject}选择题"
                q["is_real_exam"] = False
                q["id"] = f"wd-{subject[:4]}-{pnum:04d}-{q['question_number']}"
                append_jsonl(QB_FILE, q)
                total_q += 1

        if is_answer:
            info = answer_starts.get(pnum)
            if info is None:
                for ap in sorted(answer_starts.keys()):
                    if ap <= pnum:
                        info = answer_starts[ap]
            chapter = info.get("chapter", "") if info else ""
            section = info.get("section", "") if info else ""

            answers = parse_answers(text)
            if answers:
                _apply_answers(subject, chapter, section, answers, prog, key)

        prog[key]["done"].append(pnum)
        prog[key]["q_count"] = total_q
        prog[key]["kp_count"] = total_kp

        if len(prog[key]["done"]) % 10 == 0:
            save_progress(prog)
            print(f"  [{subject}] 进度 {len(prog[key]['done'])}/{len(all_target_pages)} | 题目: {total_q} | 知识点: {total_kp}")

    content_pages = {}
    if toc:
        cur_chapter = ""
        cur_section = ""
        for item in toc:
            lvl, title, page = item[0], item[1], item[2]
            if lvl == 1 and re.search(r"第.*章", title):
                cur_chapter = title
            elif lvl == 2:
                cur_section = title

        for page in range(1, total + 1):
            if page in prog[key]["done"]:
                continue
            ch = cur_chapter
            sec = cur_section
            for item in toc:
                if item[2] > page:
                    break
                if item[0] == 1 and re.search(r"第.*章", item[1]):
                    ch = item[1]
                if item[0] == 2:
                    sec = item[1]
            content_pages[page] = {"chapter": ch, "section": sec}
    else:
        sorted_ch_pages = sorted(chapter_map.keys())
        for page in range(1, total + 1):
            if page in prog[key]["done"]:
                continue
            ch = ""
            for cp in sorted_ch_pages:
                if cp <= page:
                    ch = chapter_map[cp].get("chapter", "")
                else:
                    break
            content_pages[page] = {"chapter": ch, "section": ""}

    content_processed = 0
    for pnum in sorted(content_pages.keys()):
        if pnum in prog[key]["done"]:
            continue
        if content_processed >= 200:
            break

        page = doc[pnum - 1]
        pix = page.get_pixmap(dpi=150)
        text = ocr_page(engine, pix, pnum)
        if not text:
            prog[key]["done"].append(pnum)
            continue

        info = content_pages[pnum]
        kps = extract_knowledge_points(text, subject, info["chapter"], info["section"], pnum)
        for kp in kps:
            append_jsonl(KP_FILE, kp)
            total_kp += 1

        prog[key]["done"].append(pnum)
        prog[key]["kp_count"] = total_kp
        content_processed += 1

        if content_processed % 20 == 0:
            save_progress(prog)
            print(f"  [{subject}] 知识点进度 {content_processed} | 总计KP: {total_kp}")

    doc.close()
    save_progress(prog)

    print(f"\n[{subject}] 完成!")
    print(f"  题目: {total_q} | 知识点: {total_kp}")
    return {"questions": total_q, "knowledge_points": total_kp, "matched": prog[key].get("matched", 0)}


def _apply_answers(subject: str, chapter: str, section: str, answers: dict, prog: dict, key: str) -> None:
    if not QB_FILE.exists():
        return
    lines = []
    with open(QB_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                lines.append(json.loads(line))

    updated = False
    for q in lines:
        if q.get("answer") and q["answer"].strip():
            continue
        if q.get("subject") != subject:
            continue
        qnum = q.get("question_number", "")
        if qnum in answers:
            q["answer"] = answers[qnum]["answer"]
            q["explanation"] = answers[qnum]["explanation"]
            updated = True
            prog[key]["matched"] = prog[key].get("matched", 0) + 1

    if updated:
        with open(QB_FILE, "w", encoding="utf-8") as f:
            for q in lines:
                f.write(json.dumps(q, ensure_ascii=False) + "\n")


def main() -> None:
    subjects = list(PDF_FILES.keys())
    if len(sys.argv) > 1 and sys.argv[-1] in subjects:
        subjects = [sys.argv[-1]]

    all_results = {}
    for subj in subjects:
        path = PDF_FILES[subj]
        if not path.exists():
            print(f"[跳过] 文件不存在: {path}")
            continue
        result = process_pdf(path, subj)
        all_results[subj] = result

    print(f"\n{'='*60}")
    print("全部处理完成!")
    print(json.dumps(all_results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
"""Extract knowledge points from 408 study PDFs."""
import json
import re
from pathlib import Path
import fitz

TIKU = Path("tiku")
DATA = Path("data")
OUTPUT = DATA / "knowledge_points.jsonl"

# Subject mapping based on filename
SUBJECT_MAP = {
    "数据结构": "数据结构",
    "组成原理": "计算机组成原理",
    "计网": "计算机网络",
    "操作系统": "操作系统",
}

def extract_with_cmap_fix(pdf_path):
    """Try to extract text with CMap repair for CID fonts."""
    doc = fitz.open(str(pdf_path))
    all_pages = []
    
    for page_num in range(doc.page_count):
        page = doc[page_num]
        # Try to get text using dict mode to access CIDs
        blocks = page.get_text("dict")["blocks"]
        lines = []
        for block in blocks:
            if block["type"] == 0:  # text
                for line in block.get("lines", []):
                    line_text = ""
                    for span in line.get("spans", []):
                        # Get raw text - may be garbled for CID fonts
                        line_text += span.get("text", "")
                    if line_text.strip():
                        lines.append(line_text.strip())
        all_pages.append("\n".join(lines))
    
    doc.close()
    return all_pages


def extract_images_and_ocr(pdf_path):
    """Render pages as images for OCR (pymupdf can render to pixmap)."""
    doc = fitz.open(str(pdf_path))
    pages_text = []
    
    for page_num in range(doc.page_count):
        page = doc[page_num]
        # Get text - if very short and has images, it's likely scanned
        text = page.get_text().strip()
        images = page.get_images()
        
        if len(text) < 20 and images:
            # This page is image-based, mark for OCR
            pix = page.get_pixmap(dpi=200)
            img_path = TIKU / f"_temp_page_{page_num}.png"
            pix.save(str(img_path))
            pages_text.append(f"[IMAGE_PAGE:{page_num}]")
        else:
            pages_text.append(text)
    
    doc.close()
    return pages_text


def analyze_notes_pdf(pdf_path, subject):
    """Extract structured knowledge points from notes PDFs."""
    doc = fitz.open(str(pdf_path))
    
    knowledge_points = []
    current_title = ""
    current_content = []
    current_tags = []
    page_texts = []
    
    for page_num in range(doc.page_count):
        page = doc[page_num]
        text = page.get_text().strip()
        images = page.get_images()
        page_texts.append({
            "num": page_num + 1,
            "text": text,
            "text_len": len(text),
            "images": len(images),
        })
    
    doc.close()
    return page_texts, knowledge_points


def extract_huihui_kaoyan(pdf_path):
    """Extract from 灰灰考研 94页名词解释+简答题 PDF."""
    doc = fitz.open(str(pdf_path))
    
    # Check if pages are image-based
    for i in range(min(5, doc.page_count)):
        page = doc[i]
        text = page.get_text().strip()
        images = page.get_images()
        print(f"  第{i+1}页: 文本={len(text)}字, 图片={len(images)}张, 内容='{text[:50]}'")
    
    doc.close()


def main():
    print("=" * 60)
    print("408 考研知识点提取工具")
    print("=" * 60)
    
    # Analyze 数据结构笔记
    print("\n\n1. 数据结构（总笔记）163Pq.pdf")
    print("-" * 40)
    pages, kps = analyze_notes_pdf(
        TIKU / "数据结构（总笔记）163Pq.pdf", "数据结构"
    )
    # Show some stats
    total_text_len = sum(p["text_len"] for p in pages)
    image_pages = sum(1 for p in pages if p["images"] > 0)
    print(f"  总页数: {len(pages)}")
    print(f"  含图片的页: {image_pages}")
    print(f"  总文本长度: {total_text_len}")
    print(f"  前3页文本示例:")
    for p in pages[:3]:
        print(f"    第{p['num']}页: 文本={p['text'][:80]}...")
    
    print("\n\n2. 组成原理（总笔记）156Pq.pdf")
    print("-" * 40)
    pages2, kps2 = analyze_notes_pdf(
        TIKU / "组成原理（总笔记）156Pq.pdf", "计算机组成原理"
    )
    total_text_len2 = sum(p["text_len"] for p in pages2)
    image_pages2 = sum(1 for p in pages2 if p["images"] > 0)
    print(f"  总页数: {len(pages2)}")
    print(f"  含图片的页: {image_pages2}")
    print(f"  总文本长度: {total_text_len2}")
    print(f"  前3页文本示例:")
    for p in pages2[:3]:
        print(f"    第{p['num']}页: 文本={p['text'][:80]}...")
    
    print("\n\n3. 计网（总笔记）101Pq.pdf")
    print("-" * 40)
    pages3, kps3 = analyze_notes_pdf(
        TIKU / "计网（总笔记）101Pq.pdf", "计算机网络"
    )
    total_text_len3 = sum(p["text_len"] for p in pages3)
    image_pages3 = sum(1 for p in pages3 if p["images"] > 0)
    print(f"  总页数: {len(pages3)}")
    print(f"  含图片的页: {image_pages3}")
    print(f"  总文本长度: {total_text_len3}")
    print(f"  前3页文本示例:")
    for p in pages3[:3]:
        print(f"    第{p['num']}页: 文本={p['text'][:80]}...")
    
    print("\n\n4. 【灰灰考研】94页计算机初试必背名词解释+简答题汇总-.pdf")
    print("-" * 40)
    extract_huihui_kaoyan(TIKU / "【灰灰考研】94页计算机初试必背名词解释+简答题汇总-.pdf")


if __name__ == "__main__":
    main()
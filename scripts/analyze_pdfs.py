import fitz
from pathlib import Path

tiku = Path("tiku")
pdfs = [
    "【灰灰考研】94页计算机初试必背名词解释+简答题汇总-.pdf",
    "数据结构（总笔记）163Pq.pdf",
    "组成原理（总笔记）156Pq.pdf",
    "计网（总笔记）101Pq.pdf",
]

for name in pdfs:
    path = tiku / name
    doc = fitz.open(str(path))
    print(f"\n{'='*60}")
    print(f"=== {name} ===")
    print(f"页数: {doc.page_count}")

    # 检查前3页
    for pi in range(min(3, doc.page_count)):
        page = doc[pi]
        images = page.get_images()
        text = page.get_text()
        blocks = page.get_text("dict")["blocks"]

        print(f"\n--- 第{pi+1}页 ---")
        print(f"图片数: {len(images)}")
        print(f"块数: {len(blocks)}")
        print(f"文本长度: {len(text)}")
        print(f"文本前100字: {text[:100]}")

        # 检查字体
        for b in blocks:
            if b["type"] == 0:
                for line in b.get("lines", []):
                    for span in line.get("spans", []):
                        font = span.get("font", "?")
                        size = span.get("size", 0)
                        txt = span.get("text", "")[:30]
                        print(f"  字体={font} 大小={size:.1f} 文本={txt}")
                        break
                    break
                break

    doc.close()
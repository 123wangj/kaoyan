"""Debug PDF font structure - check first objects only."""
import fitz
from pathlib import Path

TIKU = Path("tiku")
pdf_path = TIKU / "数据结构（总笔记）163Pq.pdf"
doc = fitz.open(str(pdf_path))

print("=== 对象 1-30 ===")
for xref in range(1, 31):
    try:
        obj_text = doc.xref_object(xref)
        print(f"\n#{xref}: {obj_text[:200]}")
        stream = doc.xref_stream(xref)
        if stream:
            print(f"  [流: {len(stream)} bytes]")
    except Exception as e:
        print(f"\n#{xref}: ERROR: {e}")

doc.close()
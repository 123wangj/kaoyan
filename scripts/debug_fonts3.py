"""Check full font object content."""
import fitz
from pathlib import Path

TIKU = Path("tiku")
pdf_path = TIKU / "数据结构（总笔记）163Pq.pdf"
doc = fitz.open(str(pdf_path))

for xref in [11, 19, 27]:
    obj_text = doc.xref_object(xref)
    print(f"\n=== 对象 #{xref} ===")
    print(obj_text)
    stream = doc.xref_stream(xref)
    if stream:
        print(f"  流大小: {len(stream)}")

# Also look at the descendant font inline objects - check xref stream
# The font files should be at xref 8, 16, 24, 28
print("\n\n=== 字体流对象 ===")
for xref in [8, 16, 24, 28]:
    obj_text = doc.xref_object(xref)
    print(f"\n=== 对象 #{xref} ===")
    print(obj_text[:500])
    stream = doc.xref_stream(xref)
    if stream:
        print(f"  流大小: {len(stream)}")
        # Check first bytes for TrueType signature (00010000 or OTF)
        print(f"  前16字节: {stream[:16].hex()}")

# Check if there's a ToUnicode CMap anywhere
print("\n\n=== 搜索ToUnicode/CMap ===")
xref_len = doc.xref_length()
for xref in range(1, xref_len):
    try:
        obj_text = doc.xref_object(xref)
        if 'ToUnicode' in obj_text or 'CMap' in obj_text:
            print(f"\n#{xref}: {obj_text[:200]}")
            stream = doc.xref_stream(xref)
            if stream:
                print(f"  CMap流 (前200字符): {stream[:200]}")
    except:
        pass

doc.close()
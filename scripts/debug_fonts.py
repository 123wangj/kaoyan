"""Debug PDF font structure."""
import fitz
from pathlib import Path

TIKU = Path("tiku")

pdf_path = TIKU / "数据结构（总笔记）163Pq.pdf"
doc = fitz.open(str(pdf_path))

# List all objects related to fonts
print("=== 遍历PDF对象树 ===")
xref_len = doc.xref_length()
print(f"总对象数: {xref_len}")

# Look at font-related objects
for xref in range(1, min(50, xref_len)):
    try:
        obj_text = doc.xref_object(xref)
        if any(kw in obj_text for kw in ['Font', 'font', 'CIDFont', 'ToUnicode', 'CMap']):
            print(f"\n--- 对象 #{xref} ---")
            print(obj_text[:300])
            
            # Check for streams
            stream = doc.xref_stream(xref)
            if stream:
                print(f"  流大小: {len(stream)}")
    except:
        pass

# Look at the pages
print("\n\n=== 第一页的内容流 ===")
page = doc[0]
# Get all xref objects referenced by this page
for i in range(1, min(200, xref_len)):
    try:
        obj_text = doc.xref_object(i)
        if '/FontFile' in obj_text or '/FontDescriptor' in obj_text or '/Subtype' in obj_text:
            print(f"\n--- 对象 #{i} ---")
            print(obj_text[:300])
            stream = doc.xref_stream(i)
            if stream:
                print(f"  流大小: {len(stream)}")
    except:
        pass

doc.close()
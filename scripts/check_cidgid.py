"""
Check if there's a custom CIDToGIDMap stream (not Identity).
"""
import fitz
import re
from pathlib import Path

TIKU = Path("tiku")
pdf_path = TIKU / "数据结构（总笔记）163Pq.pdf"
doc = fitz.open(str(pdf_path))

# Check the font objects more carefully
for font_name, font_xref in [("F1", 11), ("F2", 19), ("F3", 27)]:
    font_dict = doc.xref_object(font_xref)
    print(f"\n=== 字体 {font_name} (xref={font_xref}) ===")
    print(font_dict)
    
    # Check for CIDToGIDMap
    if '/CIDToGIDMap' in font_dict:
        # Check if it's a stream or Identity
        m = re.search(r'/CIDToGIDMap\s+(\d+\s+\d+\s+R|/Identity)', font_dict)
        if m:
            print(f"  CIDToGIDMap: {m.group(1)}")
            cid_gid_ref = m.group(1)
            # If it's a stream reference, extract it
            m2 = re.search(r'(\d+)\s+(\d+)\s+R', cid_gid_ref)
            if m2:
                stream_xref = int(m2.group(1))
                stream = doc.xref_stream(stream_xref)
                if stream:
                    print(f"  流大小: {len(stream)}")
                    # Parse the CIDToGIDMap stream
                    # Format: each entry is 2 bytes (big-endian)
                    if len(stream) > 20:
                        print(f"  前20个映射:")
                        for i in range(min(10, len(stream)//2)):
                            gid = (stream[i*2] << 8) | stream[i*2+1]
                            print(f"    CID {i} → GID {gid}")
    
    # Check the descendant font (inline dictionary)
    # The FontFile2 is referenced from the inline DescendantFonts dict

print("\n\n=== 检查其他所有字体对象定义 ===")
for xref in range(1, 50):
    try:
        obj_text = doc.xref_object(xref)
        if '/DescendantFonts' in obj_text or '/CIDFont' in obj_text:
            print(f"\n对象 #{xref}: {obj_text[:300]}")
    except:
        pass

doc.close()
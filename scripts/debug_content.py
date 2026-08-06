"""
Debug: Check raw content stream and understand the encoding.
"""
import fitz
import zlib
from pathlib import Path
import re

TIKU = Path("tiku")
pdf_path = TIKU / "数据结构（总笔记）163Pq.pdf"
doc = fitz.open(str(pdf_path))

page = doc[0]
contents = page.get_contents()

print(f"第1页内容流数: {len(contents)}")

for i, content_ref in enumerate(contents):
    stream = doc.xref_stream(content_ref)
    if not stream:
        continue
    try:
        data = zlib.decompress(stream)
    except:
        data = stream
    
    text = data.decode('latin-1', errors='replace')
    print(f"\n内容流 #{i} (xref={content_ref}): {len(data)} bytes decompressed")
    
    # Print first 500 chars of the raw content stream
    print(f"\n原始内容流 (前1000字符):")
    print(text[:1000])
    
    # Find all text objects
    bt_et = re.findall(r'BT(.*?)ET', text, re.DOTALL)
    print(f"\nBT/ET对象数: {len(bt_et)}")
    
    if bt_et:
        print("\n第一个BT/ET对象:")
        print(bt_et[0][:500])

doc.close()
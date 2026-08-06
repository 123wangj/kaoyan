"""
Debug: Check content stream structure of pages 1 vs 2.
"""
import fitz
import zlib
from pathlib import Path

TIKU = Path("tiku")
pdf_path = TIKU / "数据结构（总笔记）163Pq.pdf"
doc = fitz.open(str(pdf_path))

for page_num in [0, 1, 2]:
    page = doc[page_num]
    contents = page.get_contents()
    print(f"\n=== 第{page_num+1}页 ===")
    print(f"内容流数: {len(contents)}")
    
    for i, cr in enumerate(contents):
        stream = doc.xref_stream(cr)
        if not stream:
            print(f"  流 #{i}: 空")
            continue
        
        try:
            data = zlib.decompress(stream)
        except:
            data = stream
        
        text = data.decode('latin-1', errors='replace')
        print(f"  流 #{i}: {len(data)} bytes")
        print(f"  前500字符:")
        
        # Check for BT/ET and Tj/TJ
        bt_count = text.count('BT')
        et_count = text.count('ET')
        tj_count = text.count('Tj')
        TJ_count = text.count('TJ')
        print(f"  BT={bt_count}, ET={et_count}, Tj={tj_count}, TJ={TJ_count}")
        
        # Look for text content
        # Show lines with BT/ET
        lines = text.split('\n')
        for line in lines:
            if 'BT' in line or 'ET' in line or 'Tj' in line or 'TJ' in line:
                print(f"    {line.strip()[:120]}")

doc.close()
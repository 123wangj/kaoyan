"""
Use pymupdf's rawdict mode to get raw character codes,
then decode using font cmap.
"""
import fitz
import io
from fontTools.ttLib import TTFont
from pathlib import Path
import re
import zlib

TIKU = Path("tiku")


def extract_cmaps_from_pdf(doc):
    """Extract CID→Unicode cmaps from embedded fonts in a PDF."""
    page = doc[0]
    font_list = page.get_fonts()
    
    cmaps = {}
    for font_info in font_list:
        font_xref = font_info[0]
        font_res_name = font_info[4]  # e.g., 'F1'
        
        # Find the FontFile2 reference by examining the Type0 font
        try:
            font_dict = doc.xref_object(font_xref)
            # Find FontFile2 reference
            m = re.search(r'/FontFile2\s+(\d+)', font_dict)
            if m:
                ff_xref = int(m.group(1))
                stream = doc.xref_stream(ff_xref)
                if stream:
                    tt = TTFont(io.BytesIO(stream))
                    cmap_table = {}
                    for tbl in tt['cmap'].tables:
                        if hasattr(tbl, 'cmap'):
                            for cid, val in tbl.cmap.items():
                                if isinstance(val, int):
                                    cmap_table[cid] = val
                                elif isinstance(val, str):
                                    m2 = re.match(r'uni([0-9A-Fa-f]{4,})', val)
                                    if m2:
                                        cmap_table[cid] = int(m2.group(1), 16)
                    tt.close()
                    if cmap_table:
                        cmaps[font_res_name] = cmap_table
                        print(f"    字体 {font_res_name}: {len(cmap_table)} 映射")
        except Exception as e:
            print(f"    字体 {font_res_name} 错误: {e}")
    
    return cmaps


def decode_page_text(doc, page, cmaps):
    """
    Extract text from a page using rawdict and font cmap decoding.
    """
    raw = page.get_text("rawdict")
    
    page_text = []
    for block in raw.get("blocks", []):
        if block.get("type") == 0:  # text
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    font_name = span.get("font", "")
                    # Get the font resource name (e.g., 'F1')
                    # The rawdict gives us actual characters, but they're already garbled
                    pass
    
    # Alternative: try getting the raw content stream
    content_streams = page.get_contents()
    raw_cids = []
    
    for content_ref in content_streams:
        stream = doc.xref_stream(content_ref)
        if not stream:
            continue
        
        # Try to decompress
        try:
            data = zlib.decompress(stream)
        except:
            data = stream
        
        text_content = data.decode('latin-1', errors='replace')
        
        # Find text between parentheses in text objects
        # CJK text with Identity-H uses hex strings or literal bytes
        # Find all Tj text: (text) Tj
        tj_strings = re.finditer(r'\(([^)]*)\)\s*Tj', text_content)
        
        for m in tj_strings:
            raw_bytes = m.group(1).encode('latin-1')
            # In Identity-H, each character is 2 bytes (big-endian)
            for i in range(0, len(raw_bytes), 2):
                if i + 1 < len(raw_bytes):
                    cid = (raw_bytes[i] << 8) | raw_bytes[i+1]
                    raw_cids.append(cid)
        
        # Find TJ text: [(text) num (text) ...] TJ
        tj_arrays = re.finditer(r'\[(.*?)\]\s*TJ', text_content)
        for m in tj_arrays:
            inner = m.group(1)
            strings = re.findall(r'\(([^)]*)\)', inner)
            for s in strings:
                raw_bytes = s.encode('latin-1')
                for i in range(0, len(raw_bytes), 2):
                    if i + 1 < len(raw_bytes):
                        cid = (raw_bytes[i] << 8) | raw_bytes[i+1]
                        raw_cids.append(cid)
        
        # Also check if there are hex strings: <XXXX> Tj
        hex_strings = re.finditer(r'<([0-9A-Fa-f]+)>\s*Tj', text_content)
        for m in hex_strings:
            hex_str = m.group(1)
            for i in range(0, len(hex_str), 4):
                if i + 4 <= len(hex_str):
                    cid = int(hex_str[i:i+4], 16)
                    raw_cids.append(cid)
    
    # Decode using cmaps (try all available cmaps)
    decoded = []
    for cid in raw_cids:
        ch = None
        for cmap_name, cmap in cmaps.items():
            if cid in cmap:
                u = cmap[cid]
                if isinstance(u, int):
                    ch = chr(u)
                else:
                    ch = str(u)
                break
        if ch is None:
            ch = f'[{cid}]'
        decoded.append(ch)
    
    return ''.join(decoded)


def main():
    pdf_path = TIKU / "数据结构（总笔记）163Pq.pdf"
    doc = fitz.open(str(pdf_path))
    
    print("构建字体cmaps...")
    cmaps = extract_cmaps_from_pdf(doc)
    
    print(f"\n总共 {len(cmaps)} 个字体映射")
    
    for page_num in [0, 1, 2, 10, 50]:
        page = doc[page_num]
        decoded = decode_page_text(doc, page, cmaps)
        print(f"\n--- 第{page_num+1}页 ---")
        print(f"  提取结果: {decoded[:300]}")
        
        # Count Chinese characters
        chinese = sum(1 for c in decoded if '\u4e00' <= c <= '\u9fff')
        total = sum(1 for c in decoded if c != '\n' and c != ' ')
        print(f"  中文字符: {chinese}/{total}")
    
    doc.close()


if __name__ == "__main__":
    main()
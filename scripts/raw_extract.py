"""
Extract text from CID-keyed PDFs by parsing raw content streams.
This bypasses pymupdf's broken ToUnicode CMap and uses font cmap directly.
"""
import fitz
import io
import re
from fontTools.ttLib import TTFont
from pathlib import Path
import zlib

TIKU = Path("tiku")


def extract_font_cmap(doc, font_xref):
    """Extract CID→Unicode mapping from TrueType font embedded in PDF."""
    font_dict_text = doc.xref_object(font_xref)
    
    # Find FontFile2 reference in the inline DescendantFonts
    m = re.search(r'/FontDescriptor\s*<<.*?/FontFile2\s+(\d+)', font_dict_text, re.DOTALL)
    if not m:
        # Try alternate: DescendantFonts with FontDescriptor
        m = re.search(r'/FontDescriptor\s*<<.*?/FontFile2\s+(\d+)', font_dict_text, re.DOTALL)
    
    if not m:
        return None
    
    ff_xref = int(m.group(1))
    font_stream = doc.xref_stream(ff_xref)
    if not font_stream:
        return None
    
    try:
        tt = TTFont(io.BytesIO(font_stream))
        cmap = tt['cmap']
        
        cid_unicode = {}
        for table in cmap.tables:
            if hasattr(table, 'cmap'):
                for cid, value in table.cmap.items():
                    if isinstance(value, int):
                        cid_unicode[cid] = value
                    elif isinstance(value, str):
                        # 'uniXXXX' or 'uXXXX' format
                        m2 = re.match(r'uni([0-9A-Fa-f]{4,})', value)
                        if m2:
                            cid_unicode[cid] = int(m2.group(1), 16)
                        else:
                            m3 = re.match(r'u([0-9A-Fa-f]{4,})', value)
                            if m3:
                                cid_unicode[cid] = int(m3.group(1), 16)
        tt.close()
        return cid_unicode
    except Exception as e:
        print(f"    fontTools错误: {e}")
        return None


def extract_content_stream_text(content_stream_bytes, font_name_to_cmap):
    """
    Parse PDF content stream to extract text with CIDs,
    then decode using font cmap.
    """
    # Decompress if needed
    try:
        data = zlib.decompress(content_stream_bytes)
    except:
        data = content_stream_bytes
    
    text = data.decode('latin-1', errors='replace')
    
    # Remove comments
    text = re.sub(r'%.*?\n', '\n', text)
    
    # Find text objects: BT ... ET
    texts = []
    
    # Parse Tj and TJ operators
    # Tj: (text) Tj  - literal text
    # TJ: [(text) num (text)] TJ - array of text and positioning
    
    lines = []
    current_font = None
    
    # Find font changes /F1 14 Tf
    font_cmds = re.finditer(r'/(F\d+)\s+[\d.]+\s+Tf', text)
    font_positions = {}
    for m in font_cmds:
        font_positions[m.start()] = m.group(1)
    
    # Simple approach: Extract all parenthesized strings in text objects
    in_text_obj = False
    for i, line in enumerate(text.split('\n')):
        if 'BT' in line:
            in_text_obj = True
            current_line = ""
        if in_text_obj:
            # Extract (...)
            strings = re.findall(r'\(([^)]*)\)', line)
            for s in strings:
                # These are PDF literal strings - in Identity-H encoding,
                # each byte pair is a CID (2 bytes per character for CJK)
                # Convert to CIDs
                raw = s.encode('latin-1')
                cids = []
                for j in range(0, len(raw), 2):
                    if j + 1 < len(raw):
                        cid = (raw[j] << 8) | raw[j+1]
                        cids.append(cid)
                
                current_line.extend(cids)
        if 'ET' in line:
            in_text_obj = False
            if current_line:
                lines.append(current_line)
            current_line = []
    
    # If nothing found with BT/ET, try a different approach
    if not lines:
        # Try finding all parenthesized strings
        all_strings = re.findall(r'\(([^)]*)\)', text)
        for s in all_strings:
            raw = s.encode('latin-1')
            cids = []
            for j in range(0, len(raw), 2):
                if j + 1 < len(raw):
                    cid = (raw[j] << 8) | raw[j+1]
                    cids.append(cid)
            if cids:
                lines.append(cids)
    
    # Decode CIDs using font cmap
    result_lines = []
    for cid_list in lines:
        decoded = []
        for cid in cid_list:
            decoded_ch = None
            for cmap_name, cmap in font_name_to_cmap.items():
                if cid in cmap:
                    u = cmap[cid]
                    if isinstance(u, int):
                        decoded_ch = chr(u)
                    else:
                        decoded_ch = u
                    break
            if decoded_ch is None:
                decoded_ch = f'[{cid}]'
            decoded.append(decoded_ch)
        result_lines.append(''.join(decoded))
    
    return '\n'.join(result_lines)


def main():
    pdf_path = TIKU / "数据结构（总笔记）163Pq.pdf"
    doc = fitz.open(str(pdf_path))
    
    # Build font name → xref mapping from page resources
    font_name_to_xref = {}
    page = doc[0]
    resources = page.get_fonts()
    for f in resources:
        font_name_to_xref[f[4]] = f[0]  # 'F1' -> xref
    
    print(f"页面字体: {font_name_to_xref}")
    
    # Build CID→Unicode maps for each font
    font_name_to_cmap = {}
    for name, xref in font_name_to_xref.items():
        print(f"\n构建字体 {name} (xref={xref}) 的cmap...")
        cmap = extract_font_cmap(doc, xref)
        if cmap:
            print(f"  获取到 {len(cmap)} 个映射")
            font_name_to_cmap[name] = cmap
    
    if not font_name_to_cmap:
        print("无法获取任何字体映射!")
        doc.close()
        return
    
    print(f"\n{'='*60}")
    print("尝试从内容流提取文本...")
    print("="*60)
    
    # Try extracting text from page content streams
    for page_num in [0, 1, 10]:
        page = doc[page_num]
        contents = page.get_contents()
        
        print(f"\n--- 第{page_num+1}页 (内容流数: {len(contents)}) ---")
        
        all_cids = []
        for content_ref in contents:
            try:
                stream = doc.xref_stream(content_ref)
                if stream:
                    decoded = extract_content_stream_text(stream, font_name_to_cmap)
                    if decoded.strip():
                        print(f"  提取文本: {decoded[:200]}")
                        all_cids.append(decoded)
            except Exception as e:
                print(f"  解析内容流 {content_ref} 失败: {e}")
        
        # Also try pymupdf's get_text with rawdict
        raw_text = page.get_text('text')
        print(f"  pymupdf标准文本: {raw_text[:80]}")
    
    doc.close()


if __name__ == "__main__":
    main()
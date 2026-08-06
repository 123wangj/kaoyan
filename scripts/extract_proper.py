"""
Correct extraction: build INVERTED font cmap (GID → Unicode),
since CID content stream uses GIDs with Identity-H + CIDToGIDMap Identity.
"""
import fitz
import io
import re
import zlib
from fontTools.ttLib import TTFont
from pathlib import Path

TIKU = Path("tiku")


def extract_inverted_cmaps(doc):
    """Build GID→Unicode mapping from embedded TrueType font cmap.
    The TrueType cmap maps Unicode → GID (glyph ID). We invert to GID → Unicode.
    Content stream CIDs map to GIDs via CIDToGIDMap /Identity.
    """
    page = doc[0]
    font_list = page.get_fonts()
    
    cmaps = {}
    for font_info in font_list:
        font_xref = font_info[0]
        font_res_name = font_info[4]
        
        try:
            font_dict = doc.xref_object(font_xref)
            m = re.search(r'/FontFile2\s+(\d+)', font_dict)
            if m:
                ff_xref = int(m.group(1))
                stream = doc.xref_stream(ff_xref)
                if stream:
                    tt = TTFont(io.BytesIO(stream))
                    cmap_table = tt.getBestCmap()
                    tt.close()
                    
                    if cmap_table:
                        # Invert: Unicode → GID becomes GID → Unicode
                        inverted = {}
                        for unicode_char, gid in cmap_table.items():
                            if isinstance(unicode_char, int) and isinstance(gid, (int, str)):
                                if isinstance(gid, int) and gid > 0:
                                    inverted[gid] = unicode_char
                                elif isinstance(gid, str):
                                    m2 = re.match(r'uni([0-9A-Fa-f]{4,})', gid)
                                    if m2:
                                        inverted[int(m2.group(1), 16)] = unicode_char
                                    else:
                                        # Could be a named glyph like 'space'
                                        pass
                        
                        cmaps[font_res_name] = inverted
                        print(f"    字体 {font_res_name}: {len(cmaps[font_res_name])} 个GID→Unicode映射")
                        
                        # Show samples
                        for gid in sorted(inverted.keys())[:5]:
                            print(f"      GID {gid} → U+{inverted[gid]:04X} ({chr(inverted[gid])})")
                    else:
                        print(f"    字体 {font_res_name}: 无cmap")
        except Exception as e:
            print(f"    字体 {font_res_name}: {e}")
    
    return cmaps


def decode_content_stream(stream, cmaps):
    """Extract CIDs from content stream and decode using inverted cmap."""
    try:
        data = zlib.decompress(stream)
    except:
        data = stream
    
    text = data.decode('latin-1', errors='replace')
    
    # Find all text between parentheses in Tj/TJ operators
    # In Identity-H, CJK characters are stored as 2-byte octal sequences
    result = []
    
    # Find TJ arrays
    tj_arrays = re.finditer(r'\[(.*?)\]\s*TJ', text, re.DOTALL)
    for m in tj_arrays:
        inner = m.group(1)
        # Extract octal strings \xxx\xxx\xxx
        octal_strings = re.findall(r'\\([0-7]{3})', inner)
        
        bytes_list = []
        for oct_str in octal_strings:
            bytes_list.append(int(oct_str, 8))
        
        # Decode as 2-byte big-endian CIDs
        cids = []
        for i in range(0, len(bytes_list), 2):
            if i + 1 < len(bytes_list):
                cid = (bytes_list[i] << 8) | bytes_list[i+1]
                cids.append(cid)
        
        # Try to decode using all available cmaps
        for cid in cids:
            decoded = None
            for cmap in cmaps.values():
                if cid in cmap:
                    decoded = chr(cmap[cid])
                    break
            if decoded is None:
                decoded = f'[{cid}]'
            result.append(decoded)
    
    return ''.join(result)


def main():
    pdf_paths = [
        ("数据结构（总笔记）163Pq.pdf", "数据结构"),
        ("组成原理（总笔记）156Pq.pdf", "计算机组成原理"),
        ("计网（总笔记）101Pq.pdf", "计算机网络"),
    ]
    
    for pdf_name, subject in pdf_paths:
        print(f"\n{'='*60}")
        print(f"=== {pdf_name} ===")
        print('='*60)
        
        pdf_path = TIKU / pdf_name
        if not pdf_path.exists():
            print(f"文件不存在，跳过")
            continue
        
        doc = fitz.open(str(pdf_path))
        print("\n构建GID→Unicode映射...")
        cmaps = extract_inverted_cmaps(doc)
        
        if not cmaps:
            print("无可用映射!")
            doc.close()
            continue
        
        # Try decoding a few pages
        for page_num in [0, 1, 2]:
            page = doc[page_num]
            contents = page.get_contents()
            
            page_text = []
            for content_ref in contents:
                stream = doc.xref_stream(content_ref)
                if stream:
                    decoded = decode_content_stream(stream, cmaps)
                    if decoded:
                        page_text.append(decoded)
            
            full_text = '\n'.join(page_text)
            chinese = sum(1 for c in full_text if '\u4e00' <= c <= '\u9fff')
            print(f"\n  第{page_num+1}页:")
            print(f"  提取文本: {full_text[:300]}")
            print(f"  中文字符: {chinese}/{max(1, len(full_text.strip()))}")
        
        doc.close()


if __name__ == "__main__":
    main()
"""
Build correct GID→Unicode mapping by extracting raw format 4 cmap.
"""
import fitz
import io
from fontTools.ttLib import TTFont
from pathlib import Path
import re

TIKU = Path("tiku")

def build_gid_to_unicode(font_stream):
    """Build GID→Unicode from TrueType cmap.
    Format 4 cmap stores: {unicode_codepoint: glyph_id}
    We need to invert this to: {glyph_id: unicode_codepoint}
    """
    tt = TTFont(io.BytesIO(font_stream))
    
    cmap = tt['cmap']
    gid_to_unicode = {}
    
    for table in cmap.tables:
        if hasattr(table, 'cmap'):
            for unicode_char, glyph_val in table.cmap.items():
                # glyph_val could be int (glyph index) or str (glyph name)
                if isinstance(glyph_val, int):
                    gid_to_unicode[glyph_val] = unicode_char
                elif isinstance(glyph_val, str):
                    # Try to get the actual glyph index for this name
                    try:
                        gid = tt.getGlyphID(glyph_val)
                        gid_to_unicode[gid] = unicode_char
                    except KeyError:
                        pass
    
    tt.close()
    return gid_to_unicode


def decode_content_cids(cids_list, gid_to_unicode):
    """Decode a list of CIDs using GID→Unicode mapping.
    With CIDToGIDMap /Identity, CID = GID.
    """
    result = []
    for cid in cids_list:
        if cid in gid_to_unicode:
            u = gid_to_unicode[cid]
            result.append(chr(u) if isinstance(u, int) else str(u))
        else:
            result.append(f'[{cid}]')
    return ''.join(result)


def extract_cids_from_content_stream(stream):
    """Extract CIDs from a PDF content stream."""
    import zlib
    try:
        data = zlib.decompress(stream)
    except:
        data = stream
    
    text = data.decode('latin-1', errors='replace')
    
    # Find TJ arrays with octal strings
    cids = []
    tj_arrays = re.finditer(r'\[(.*?)\]\s*TJ', text, re.DOTALL)
    for m in tj_arrays:
        inner = m.group(1)
        octal_strings = re.findall(r'\\([0-7]{3})', inner)
        bytes_list = [int(o, 8) for o in octal_strings]
        
        for i in range(0, len(bytes_list), 2):
            if i + 1 < len(bytes_list):
                cid = (bytes_list[i] << 8) | bytes_list[i+1]
                cids.append(cid)
    
    return cids


def main():
    pdfs = [
        ("数据结构（总笔记）163Pq.pdf", "数据结构"),
        ("组成原理（总笔记）156Pq.pdf", "计算机组成原理"),
        ("计网（总笔记）101Pq.pdf", "计算机网络"),
    ]
    
    for pdf_name, subject in pdfs:
        print(f"\n{'='*60}")
        print(f"=== {pdf_name} ===")
        
        pdf_path = TIKU / pdf_name
        doc = fitz.open(str(pdf_path))
        
        # Build GID→Unicode for each font
        page = doc[0]
        fonts = page.get_fonts()
        
        all_gid_maps = {}
        for f in fonts:
            font_xref = f[0]
            font_res = f[4]
            font_dict = doc.xref_object(font_xref)
            m = re.search(r'/FontFile2\s+(\d+)', font_dict)
            if m:
                ff_xref = int(m.group(1))
                stream = doc.xref_stream(ff_xref)
                if stream:
                    gid_map = build_gid_to_unicode(stream)
                    if gid_map:
                        all_gid_maps[font_res] = gid_map
                        # Check GID range
                        gids = sorted(gid_map.keys())
                        print(f"  字体 {font_res}: {len(gid_map)}映射, GID范围 {gids[0]}-{gids[-1]}")
        
        # Decode first few pages
        for page_num in [0, 1, 2, 3, 4]:
            page = doc[page_num]
            contents = page.get_contents()
            
            all_cids = []
            for cr in contents:
                s = doc.xref_stream(cr)
                if s:
                    cids = extract_cids_from_content_stream(s)
                    all_cids.extend(cids)
            
            # Try each font's GID map
            best_decoded = ""
            best_chinese = 0
            for font_name, gid_map in all_gid_maps.items():
                decoded = decode_content_cids(all_cids, gid_map)
                chinese = sum(1 for c in decoded if '\u4e00' <= c <= '\u9fff')
                if chinese > best_chinese:
                    best_chinese = chinese
                    best_decoded = decoded
            
            print(f"\n  第{page_num+1}页: CIDs={len(all_cids)}, 中文字符={best_chinese}")
            if best_decoded:
                print(f"  内容: {best_decoded[:200]}")
        
        doc.close()


if __name__ == "__main__":
    main()
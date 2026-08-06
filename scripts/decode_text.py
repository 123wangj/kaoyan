"""Extract CID→Unicode mapping from embedded fonts and ToUnicode CMaps."""
import fitz
import io
import re
from fontTools.ttLib import TTFont
from pathlib import Path

TIKU = Path("tiku")


def decode_cmap_stream(stream):
    """Decode a ToUnicode CMap stream (may be FlateDecode compressed)."""
    # CMap streams are in PDF content format
    try:
        text = stream.decode('utf-8', errors='replace')
    except:
        text = stream.decode('latin-1', errors='replace')
    return text


def build_cmap_from_text(cmap_text):
    """Parse a ToUnicode CMap and extract CID→Unicode mappings."""
    mapping = {}
    # Look for patterns like: <CID> <Unicode>
    # Common formats:
    # 1 begincodespacerange <00> <FF> endcodespacerange
    # 2 beginbfchar <0001> <0020> endbfchar
    # 3 beginbfrange <0000> <0019> <0020> endbfrange
    
    # Pattern for bfchar: <XXXX> <YYYY>
    bfchar_pattern = re.findall(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', cmap_text)
    for cid_str, uni_str in bfchar_pattern:
        cid = int(cid_str, 16)
        unicode_val = int(uni_str, 16)
        mapping[cid] = unicode_val
    
    # Pattern for bfrange: <XXXX> <YYYY> <ZZZZ>
    bfrange_pattern = re.findall(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', cmap_text)
    for start_str, end_str, base_str in bfrange_pattern:
        start = int(start_str, 16)
        end = int(end_str, 16)
        base = int(base_str, 16)
        for i in range(start, end + 1):
            mapping[i] = base + (i - start)
    
    return mapping


def build_cmap_from_truetype(font_stream):
    """Build CID→Unicode mapping from embedded TrueType font cmap."""
    try:
        tt = TTFont(io.BytesIO(font_stream))
        cmap = tt.getBestCmap()
        tt.close()
        return cmap
    except Exception as e:
        print(f"    TrueType解析失败: {e}")
        return None


def decode_text_with_mapping(text, cid_map):
    """Decode garbled text using CID→Unicode mapping.
    
    In Identity-H encoding, the characters in the PDF text are stored as
    Unicode code points that correspond to the CID values.
    """
    result = []
    for ch in text:
        code = ord(ch)
        if code in cid_map:
            u = cid_map[code]
            if isinstance(u, int):
                result.append(chr(u))
            else:
                result.append(u)
        else:
            result.append(ch)
    return ''.join(result)


def main():
    pdf_path = TIKU / "数据结构（总笔记）163Pq.pdf"
    doc = fitz.open(str(pdf_path))
    
    # Font file xrefs
    font_configs = [
        {"font_file": 8, "cmap": 10, "name": "CIDFont+F1"},
        {"font_file": 16, "cmap": 18, "name": "CIDFont+F2"},
        {"font_file": 24, "cmap": 26, "name": "CIDFont+F3"},
    ]
    
    for cfg in font_configs:
        print(f"\n=== {cfg['name']} ===")
        
        # Extract ToUnicode CMap
        cmap_stream = doc.xref_stream(cfg["cmap"])
        if cmap_stream:
            cmap_text = cmap_stream.decode('latin-1', errors='replace')
            print(f"  原始CMap内容:")
            print(f"  {cmap_text[:300]}")
            
            mapping = build_cmap_from_text(cmap_text)
            print(f"  解析出 {len(mapping)} 个映射")
            if mapping:
                for k in list(mapping.keys())[:5]:
                    print(f"    CID {k} → U+{mapping[k]:04X} ({chr(mapping[k])})")
        else:
            print(f"  无法读取CMap")
        
        # Extract TrueType font
        font_stream = doc.xref_stream(cfg["font_file"])
        if font_stream:
            print(f"  字体流大小: {len(font_stream)}")
            tt_cmap = build_cmap_from_truetype(font_stream)
            if tt_cmap:
                print(f"  TrueType cmap: {len(tt_cmap)} 个映射")
                # Check if values are int or str
                val_types = set(type(v).__name__ for v in tt_cmap.values())
                print(f"  值类型: {val_types}")
                for k in list(tt_cmap.keys())[:5]:
                    u = tt_cmap[k]
                    if isinstance(u, int):
                        print(f"    CID {k} → U+{u:04X}")
                    else:
                        print(f"    CID {k} → {repr(u)}")
                
                # Try decoding page 1 text
                page0 = doc[0]
                text = page0.get_text()
                decoded = decode_text_with_mapping(text, tt_cmap)
                print(f"\n  解码结果 (TrueType cmap):")
                print(f"  {decoded[:300]}")
                # Check if decoded looks like Chinese
                chinese_chars = sum(1 for c in decoded if '\u4e00' <= c <= '\u9fff')
                print(f"  中文字符数: {chinese_chars}/{len(decoded.strip())}")
    
    doc.close()


if __name__ == "__main__":
    main()
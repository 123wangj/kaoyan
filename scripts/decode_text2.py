"""Extract CID→Unicode mapping from TrueType cmap with glyph names."""
import fitz
import io
import re
from fontTools.ttLib import TTFont
from pathlib import Path

TIKU = Path("tiku")

def build_cmap_from_truetype(font_stream):
    """Build CID→Unicode mapping from TrueType font cmap table.
    Handle both format 4 (int→int) and format 1/3 (int→str with uniXXXX names)."""
    try:
        tt = TTFont(io.BytesIO(font_stream))
        
        # Get the cmap table
        cmap = tt['cmap']
        
        cid_map = {}
        
        for table in cmap.tables:
            if hasattr(table, 'cmap'):
                for cid, value in table.cmap.items():
                    if isinstance(value, int):
                        # Direct Unicode mapping
                        cid_map[cid] = value
                    elif isinstance(value, str):
                        # PostScript glyph name - check for uniXXXX pattern
                        if value.startswith('uni') and len(value) == 7:
                            try:
                                unicode_val = int(value[3:], 16)
                                cid_map[cid] = unicode_val
                            except:
                                cid_map[cid] = None
                        elif value.startswith('u') and len(value) > 1:
                            try:
                                unicode_val = int(value[1:], 16)
                                cid_map[cid] = unicode_val
                            except:
                                cid_map[cid] = None
        
        tt.close()
        return cid_map
    except Exception as e:
        print(f"    TrueType解析失败: {e}")
        return None


def decode_text_with_mapping(text, cid_map):
    """Decode garbled text using CID→Unicode mapping."""
    result = []
    for ch in text:
        code = ord(ch)
        if code in cid_map:
            u = cid_map[code]
            if u is None:
                result.append(ch)
            elif isinstance(u, int):
                result.append(chr(u))
            else:
                result.append(u)
        else:
            result.append(ch)
    return ''.join(result)


def main():
    pdf_path = TIKU / "数据结构（总笔记）163Pq.pdf"
    doc = fitz.open(str(pdf_path))
    
    font_configs = [
        {"font_file": 8, "name": "CIDFont+F1"},
        {"font_file": 16, "name": "CIDFont+F2"},
        {"font_file": 24, "name": "CIDFont+F3"},
    ]
    
    for cfg in font_configs:
        print(f"\n=== {cfg['name']} ===")
        font_stream = doc.xref_stream(cfg["font_file"])
        if font_stream:
            print(f"  字体流大小: {len(font_stream)}")
            cid_map = build_cmap_from_truetype(font_stream)
            if cid_map:
                # Remove None values
                valid_map = {k: v for k, v in cid_map.items() if v is not None}
                print(f"  有效映射: {len(valid_map)}/{len(cid_map)}")
                
                # Show some Chinese character mappings
                chinese_items = []
                for k, v in valid_map.items():
                    if 0x4E00 <= v <= 0x9FFF:
                        chinese_items.append((k, v))
                print(f"  中文字符映射: {len(chinese_items)}")
                if chinese_items:
                    for k, v in chinese_items[:10]:
                        print(f"    CID {k} → U+{v:04X} ({chr(v)})")
                
                # Try decoding page 1 text
                page0 = doc[0]
                text = page0.get_text()
                decoded = decode_text_with_mapping(text, valid_map)
                print(f"\n  解码结果:")
                print(f"  {decoded[:500]}")
                chinese_chars = sum(1 for c in decoded if '\u4e00' <= c <= '\u9fff' or '\u3000' <= c <= '\u303f' or '\uff00' <= c <= '\uffef')
                print(f"  中文字符数: {chinese_chars}/{len(decoded.strip())}")
            else:
                print(f"  无法构建映射")
    
    doc.close()


if __name__ == "__main__":
    main()
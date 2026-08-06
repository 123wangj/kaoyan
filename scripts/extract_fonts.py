"""Extract embedded TrueType fonts from CID font PDFs and decode text."""
import fitz
import io
import re
from fontTools.ttLib import TTFont
from pathlib import Path

TIKU = Path("tiku")


def extract_font_stream(doc, font_xref):
    """Extract font stream from a PDF font reference."""
    font_dict_text = doc.xref_object(font_xref)
    
    # Check if this is a Type0 font with DescendantFonts
    desc_match = re.search(r'/DescendantFonts\s*\[(\d+)', font_dict_text)
    if desc_match:
        desc_xref = int(desc_match.group(1))
        desc_text = doc.xref_object(desc_xref)
        
        # Check for FontDescriptor in the descendant
        fd_match = re.search(r'/FontDescriptor\s+(\d+)', desc_text)
        if fd_match:
            fd_xref = int(fd_match.group(1))
            # Check for FontFile2 (embedded TrueType) or FontFile (Type1)
            for key in ['/FontFile2', '/FontFile', '/FontFile3']:
                ff_match = re.search(rf'{key}\s+(\d+)', doc.xref_object(fd_xref))
                if ff_match:
                    ff_xref = int(ff_match.group(1))
                    stream = doc.xref_stream(ff_xref)
                    if stream and len(stream) > 100:
                        return stream, key
    return None, None


def build_cid_map_from_font(font_stream):
    """Build CID→Unicode mapping from embedded TrueType font."""
    try:
        tt = TTFont(io.BytesIO(font_stream))
        cmap = tt.getBestCmap()
        tt.close()
        return cmap
    except Exception as e:
        print(f"    字体解析失败: {e}")
        return None


def decode_text(text, cid_map):
    """Decode garbled text using CID→Unicode mapping."""
    result = []
    for ch in text:
        code = ord(ch)
        if code in cid_map:
            u = cid_map[code]
            result.append(chr(u) if isinstance(u, int) else u)
        else:
            # Keep original if not in map
            result.append(ch)
    return ''.join(result)


def main():
    pdfs = [
        ("数据结构（总笔记）163Pq.pdf", "数据结构"),
        ("组成原理（总笔记）156Pq.pdf", "计算机组成原理"),
        ("计网（总笔记）101Pq.pdf", "计算机网络"),
    ]
    
    all_cid_maps = {}
    
    for pdf_name, subject in pdfs:
        print(f"\n=== {pdf_name} ===")
        doc = fitz.open(str(TIKU / pdf_name))
        page = doc[0]
        fonts = page.get_fonts()
        
        font_streams = []
        
        for font_info in fonts:
            font_xref = font_info[0]
            font_name = font_info[3] if len(font_info) > 3 else str(font_xref)
            print(f"\n  处理字体: name={font_name}, xref={font_xref}")
            
            stream, key = extract_font_stream(doc, font_xref)
            if stream:
                print(f"    提取到字体流: {key}, 大小={len(stream)}")
                cmap = build_cid_map_from_font(stream)
                if cmap:
                    print(f"    成功构建cmap: {len(cmap)}个映射")
                    # Show sample
                    for cid in list(cmap.keys())[:5]:
                        u = cmap[cid]
                        print(f"      CID {cid} → U+{u:04X} ({chr(u) if u < 0x10000 else '?'})")
                    all_cid_maps[font_name] = cmap
                else:
                    print(f"    无法构建cmap")
            else:
                print(f"    无法提取字体流")
        
        # Try to decode page 1 text
        if all_cid_maps:
            page0_text = doc[0].get_text()
            # Try all cmaps
            for name, cmap in all_cid_maps.items():
                decoded = decode_text(page0_text, cmap)
                print(f"\n  使用{name}解码:")
                print(f"  {decoded[:200]}")
        
        doc.close()
    
    return all_cid_maps


if __name__ == "__main__":
    main()
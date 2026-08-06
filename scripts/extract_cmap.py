"""Extract CID-to-Unicode mapping from embedded fonts in the PDF."""
import fitz
from fontTools.ttLib import TTFont
from pathlib import Path
import io
import json

TIKU = Path("tiku")
DATA = Path("data")

def extract_font_cmap(pdf_path, subject):
    """Extract CID→Unicode mapping from embedded fonts."""
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    fonts = page.get_fonts()
    
    cid_map = {}
    
    for font_info in fonts:
        font_name = font_info[0]  # e.g., "CIDFont+F1"
        font_type = font_info[1]  # e.g., "ttf"
        font_xref = font_info[3]  # PDF xref number
        
        print(f"  字体: {font_name} (xref={font_xref}, type={font_type})")
        
        try:
            # Extract the font file stream from PDF
            font_stream = doc.xref_stream(font_xref)
            if font_stream is None:
                # The font might be referenced through a descendant font
                # Try to get the font dictionary and find the descendant font
                font_dict_text = doc.xref_object(font_xref)
                print(f"    字典: {font_dict_text[:200]}")
                
                # Look for DescendantFonts reference
                import re
                desc_match = re.search(r'/DescendantFonts\s*\[(\d+)\s+\d', font_dict_text)
                if desc_match:
                    desc_xref = int(desc_match.group(1))
                    desc_text = doc.xref_object(desc_xref)
                    print(f"    子字体字典: {desc_text[:200]}")
                    
                    # Look for FontDescriptor
                    fd_match = re.search(r'/FontDescriptor\s+(\d+)', desc_text)
                    if fd_match:
                        fd_xref = int(fd_match.group(1))
                        fd_text = doc.xref_object(fd_xref)
                        print(f"    字体描述: {fd_text[:200]}")
                        
                        # Look for FontFile2 (embedded TrueType)
                        ff_match = re.search(r'/FontFile2\s+(\d+)', fd_text)
                        if ff_match:
                            ff_xref = int(ff_match.group(1))
                            font_stream = doc.xref_stream(ff_xref)
                            print(f"    FontFile2 xref={ff_xref}, size={len(font_stream) if font_stream else 0}")
            else:
                print(f"    直接字体流, 大小={len(font_stream)}")
            
            if font_stream:
                # Parse the TrueType font with fontTools
                try:
                    tt = TTFont(io.BytesIO(font_stream))
                    
                    # Check if there's a cmap table
                    if 'cmap' in tt:
                        cmap = tt['cmap']
                        # Get the best cmap table (3,1 or 0,3 for Windows Unicode BMP)
                        for table in cmap.tables:
                            if hasattr(table, 'format') and hasattr(table, 'platformID'):
                                print(f"    cmap表: platformID={table.platformID}, platEncID={table.platEncID}, format={table.format}")
                        
                        # Build mapping from the best cmap
                        best_cmap = cmap.getBestCmap()
                        if best_cmap:
                            print(f"    cmap条目数: {len(best_cmap)}")
                            # Sample mappings
                            items = list(best_cmap.items())[:5]
                            for k, v in items:
                                print(f"      CID {k} → U+{v:04X} ({chr(v) if v < 0x10000 else '?'})")
                            cid_map = best_cmap
                        else:
                            print(f"    没有有效的cmap")
                    else:
                        print(f"    没有cmap表")
                    
                    # Check what tables are available
                    tables = tt.keys()
                    print(f"    可用表: {tables}")
                    
                    tt.close()
                except Exception as e:
                    print(f"    解析字体失败: {e}")
        except Exception as e:
            print(f"    提取字体失败: {e}")
    
    doc.close()
    return cid_map


def try_decode_with_cmap(text, cid_map):
    """Try to decode garbled text using CID mapping."""
    # The garbled characters are actually individual Unicode characters
    # that map to CIDs. We need to extract the CIDs from the text.
    # In Identity-H, the CIDs are the character codes used directly.
    result = []
    for ch in text:
        code = ord(ch)
        if code in cid_map:
            unicode_val = cid_map[code]
            result.append(chr(unicode_val) if isinstance(unicode_val, int) else unicode_val)
        else:
            result.append(ch)
    return ''.join(result)


def main():
    print("=" * 60)
    print("提取PDF字体CID映射")
    print("=" * 60)
    
    pdfs = [
        ("数据结构（总笔记）163Pq.pdf", "数据结构"),
        ("组成原理（总笔记）156Pq.pdf", "计算机组成原理"),
        ("计网（总笔记）101Pq.pdf", "计算机网络"),
    ]
    
    for pdf_name, subject in pdfs:
        print(f"\n--- {pdf_name} ---")
        cid_map = extract_font_cmap(TIKU / pdf_name, subject)
        
        # Try to decode some text
        doc = fitz.open(str(TIKU / pdf_name))
        page = doc[0]
        text = page.get_text()
        if cid_map:
            decoded = try_decode_with_cmap(text, cid_map)
            print(f"\n  解码结果前200字:")
            print(f"  {decoded[:200]}")
        doc.close()


if __name__ == "__main__":
    main()
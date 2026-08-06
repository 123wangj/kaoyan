"""
Try to build a mapping by looking at the font's post table (glyph names)
and/or extracting the cmap table in different formats.
"""
import fitz
import io
from fontTools.ttLib import TTFont
from pathlib import Path
import re

TIKU = Path("tiku")
pdf_path = TIKU / "数据结构（总笔记）163Pq.pdf"
doc = fitz.open(str(pdf_path))

# Get font stream for F1 (xref=8)
font_stream = doc.xref_stream(8)
if font_stream:
    tt = TTFont(io.BytesIO(font_stream))
    
    print("=== TrueType Font Tables ===")
    print(f"Available tables: {tt.keys()}")
    
    # Check cmap in detail
    if 'cmap' in tt:
        cmap = tt['cmap']
        print(f"\n=== cmap table ({len(cmap.tables)} subtables) ===")
        for i, table in enumerate(cmap.tables):
            print(f"\nSubtable #{i}:")
            print(f"  platformID={table.platformID}, platEncID={table.platEncID}")
            print(f"  format={table.format}, language={table.language}")
            if hasattr(table, 'cmap'):
                print(f"  entries: {len(table.cmap)}")
                # Show sample entries
                sample = list(table.cmap.items())[:3]
                for k, v in sample:
                    print(f"    {k} → {repr(v)}")
    
    # Check post table for glyph names
    if 'post' in tt:
        post = tt['post']
        print(f"\n=== post table ===")
        print(f"  format: {post.formatType}")
        if hasattr(post, 'glyphNames'):
            names = post.getGlyphNames()
            print(f"  glyph names: {len(names)}")
            # Show sample
            for name in names[:10]:
                print(f"    {name}")
    
    # Check if there's a CFF table (for CID-keyed fonts)
    if 'CFF ' in tt:
        print(f"\n=== CFF table present ===")
    
    # Check the number of glyphs
    if 'maxp' in tt:
        print(f"\n=== maxp table ===")
        print(f"  numGlyphs: {tt['maxp'].numGlyphs}")
    
    # Check the full font name
    if 'name' in tt:
        name = tt['name']
        print(f"\n=== name table ===")
        for record in name.names:
            if record.nameID in [1, 2, 4, 6]:
                try:
                    print(f"  nameID={record.nameID}: {record.toUnicode()}")
                except:
                    pass
    
    # Try format 4 cmap - keys might be in a different encoding
    for table in cmap.tables:
        if hasattr(table, 'cmap') and table.format == 4:
            print(f"\n=== Format 4 subtable (platformID={table.platformID}) ===")
            # Format 4 keys are 2-byte character codes
            # We need to build a proper {cid: unicode} mapping
            # But the keys in the cmap might NOT be CIDs
            # They could be Unicode code points mapped to different GIDs
            
            # Let me look at ALL entries to understand the mapping pattern
            cid_gid = {}
            for code, gid in table.cmap.items():
                cid_gid[code] = gid
            
            # Check if CIDs match content stream values
            # Content stream CIDs are small numbers (500-8000)
            cmap_cids = sorted(cid_gid.keys())[:20]
            print(f"  Min CID key: {min(cmap_cids)}")
            print(f"  Max CID key in sample: {cmap_cids[-1]}")
            
            # Get GID values 
            gid_values = sorted(set(cid_gid.values()))[:20]
            print(f"  GID range sample: {gid_values}")
            
            # Check: do keys follow Unicode pattern?
            unicode_keys = [k for k in cid_gid.keys() if 0x4E00 <= k <= 0x9FFF]
            print(f"  CJK Unicode keys: {len(unicode_keys)}")
            if unicode_keys:
                for k in unicode_keys[:5]:
                    print(f"    U+{k:04X} ({chr(k)}) → GID {cid_gid[k]}")
    
    tt.close()

doc.close()
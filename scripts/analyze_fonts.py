"""Try to fix CID font extraction by examining PDF font structures."""
import fitz
from pathlib import Path

TIKU = Path("tiku")
pdf_path = TIKU / "数据结构（总笔记）163Pq.pdf"

doc = fitz.open(str(pdf_path))

# Check font info from the PDF catalog
xref = doc.pdf_catalog()
page = doc[0]

# Get all fonts used
fonts = page.get_fonts()
print("第1页使用的字体:")
for f in fonts:
    print(f"  {f}")

# Check if there's a ToUnicode CMap
for page_num in [0, 1, 10, 50]:
    page = doc[page_num]
    text = page.get_text("text")
    images = page.get_images()
    
    # Also try to extract with different flags
    # TEXT_PRESERVE_LIGATURES = 1
    # TEXT_PRESERVE_WHITESPACE = 2
    # TEXT_PRESERVE_IMAGES = 4
    # TEXT_INHIBIT_SPACES = 8
    # TEXT_DEHYPHENATE = 16
    
    text2 = page.get_text("text", flags=0)
    
    print(f"\n第{page_num+1}页: images={len(images)}")
    print(f"  标准模式: {text[:60]}...")
    print(f"  flags=0: {text2[:60]}...")

doc.close()
print("\n\n尝试分析PDF的内部结构...")

# Use low-level PDF access
doc2 = fitz.open(str(pdf_path))
page = doc2[0]
# Get the page's content stream as text
try:
    xref = page.get_contents()[0]
    content = doc2.xref_stream(xref)
    # Look for font references in the content stream
    content_str = content.decode('latin-1')
    # Find font references
    font_refs = []
    for line in content_str.split('\n'):
        if 'Font' in line or 'Tf' in line:
            font_refs.append(line.strip()[:100])
    print(f"\n内容流中的字体引用:")
    for ref in font_refs[:10]:
        print(f"  {ref}")
except Exception as e:
    print(f"无法解析内容流: {e}")
doc2.close()

print("\n尝试查看字体对象的ToUnicode信息...")
doc3 = fitz.open(str(pdf_path))
page = doc3[0]
fonts = page.get_fonts()
for f in fonts:
    font_xref = f[3]  # xref
    try:
        font_dict = doc3.xref_object(font_xref)
        print(f"\n字体对象 #{font_xref}:")
        print(f"  {font_dict[:200]}")
    except:
        pass
doc3.close()
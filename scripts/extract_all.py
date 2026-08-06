# Extract structured knowledge points from all notes PDFs
import fitz
import io
import re
import zlib
import json
from fontTools.ttLib import TTFont
from pathlib import Path

TIKU = Path("tiku")
DATA = Path("data")


def build_font_cmaps(doc):
    page = doc[0]
    fonts = page.get_fonts()
    gid_maps = {}
    for f in fonts:
        font_res = f[4]
        font_xref = f[0]
        font_dict = doc.xref_object(font_xref)
        m = re.search(r'/FontFile2\s+(\d+)', font_dict)
        if m:
            ff_xref = int(m.group(1))
            stream = doc.xref_stream(ff_xref)
            if stream:
                try:
                    tt = TTFont(io.BytesIO(stream))
                    cmap = tt['cmap']
                    gid_unicode = {}
                    for table in cmap.tables:
                        if hasattr(table, 'cmap'):
                            for unicode_char, glyph_val in table.cmap.items():
                                if isinstance(glyph_val, int):
                                    gid_unicode[glyph_val] = unicode_char
                                elif isinstance(glyph_val, str):
                                    try:
                                        gid = tt.getGlyphID(glyph_val)
                                        gid_unicode[gid] = unicode_char
                                    except KeyError:
                                        pass
                    tt.close()
                    if gid_unicode:
                        gid_maps[font_res] = gid_unicode
                except:
                    pass
    return gid_maps


def decode_cids(cids, gid_maps):
    result = []
    for cid in cids:
        ch = None
        for gid_map in gid_maps.values():
            if cid in gid_map:
                u = gid_map[cid]
                ch = chr(u) if isinstance(u, int) else str(u)
                break
        if ch is None:
            ch = ''
        result.append(ch)
    return ''.join(result)


def extract_page_text(doc, page, gid_maps):
    contents = page.get_contents()
    all_cids = []
    for content_ref in contents:
        stream = doc.xref_stream(content_ref)
        if not stream:
            continue
        try:
            data = zlib.decompress(stream)
        except:
            data = stream
        text = data.decode('latin-1', errors='replace')
        tj_arrays = re.finditer(r'\[(.*?)\]\s*TJ', text, re.DOTALL)
        for m in tj_arrays:
            inner = m.group(1)
            hex_strings = re.findall(r'<([0-9A-Fa-f]+)>', inner)
            for hex_str in hex_strings:
                for i in range(0, len(hex_str), 4):
                    if i + 4 <= len(hex_str):
                        cid = int(hex_str[i:i+4], 16)
                        all_cids.append(cid)
            oct_strings = re.findall(r'\\([0-7]{3})', inner)
            bytes_list = []
            for oct_str in oct_strings:
                bytes_list.append(int(oct_str, 8))
            for i in range(0, len(bytes_list), 2):
                if i + 1 < len(bytes_list):
                    cid = (bytes_list[i] << 8) | bytes_list[i+1]
                    all_cids.append(cid)
        hex_tj = re.finditer(r'<([0-9A-Fa-f]+)>\s*Tj', text)
        for m in hex_tj:
            hex_str = m.group(1)
            for i in range(0, len(hex_str), 4):
                if i + 4 <= len(hex_str):
                    cid = int(hex_str[i:i+4], 16)
                    all_cids.append(cid)
    return decode_cids(all_cids, gid_maps)


def extract_all_pages(pdf_path):
    doc = fitz.open(str(pdf_path))
    gid_maps = build_font_cmaps(doc)
    if not gid_maps:
        doc.close()
        return []
    pages_text = []
    for page_num in range(doc.page_count):
        page = doc[page_num]
        text = extract_page_text(doc, page, gid_maps)
        pages_text.append(text)
    doc.close()
    return pages_text


def structure_knowledge_points(pages_text, subject):
    """Parse extracted text into structured knowledge points.
    Uses multiple strategies to extract meaningful knowledge entries from each page.
    """
    kps = []
    seen_titles = set()
    
    for page_idx, text in enumerate(pages_text):
        if not text.strip():
            continue
        
        page_num = page_idx + 1
        
        # Strategy 1: Find all numbered/labeled sections within the page
        # Match patterns like: 1.xxx, 一、xxx, 【xxx】, 数字、xxx
        sections = []
        
        # Pattern: Chinese number + punctuation (一、, 二、, etc or １、, ２、 etc)
        pattern1 = r'(?:^|(?<=[。；\n]))\s*([一二三四五六七八九十百]+[、.．]\s*[^\n。；]{2,60})'
        matches = list(re.finditer(pattern1, text))
        for m in matches:
            sections.append((m.start(), m.group(1).strip()))
        
        # Pattern: Arabic numeral + punctuation (1., 2.、etc)
        pattern2 = r'(?:^|(?<=[。；\n]))\s*(\d+[、.．]\s*[^\n。；]{2,60})'
        matches = list(re.finditer(pattern2, text))
        for m in matches:
            sections.append((m.start(), m.group(1).strip()))
        
        # Pattern: Keywords as titles
        keywords = ['定义', '概念', '特点', '分类', '原理', '应用', '总结', '结构', '算法', 
                    '排序', '查找', '遍历', '存储', '链表', '队列', '栈', '树', '图',
                    '线性表', '串', '数组', '矩阵', '哈希', '堆', '二叉树', 'B树',
                    '指令', '总线', '中断', 'DMA', 'Cache', 'TLB', '页表', '段页',
                    '流水线', '并行', '冲突', '冒险', '互斥', '同步', '异步',
                    '寻址', '寻址方式', '数据表示', '运算', '溢出', '移位',
                    '存储器', '主存', 'ROM', 'RAM', '硬盘', '磁盘', '通道',
                    'I/O', '接口', '外设', '显示器', '打印机', '键盘',
                    '操作系统', '进程', '线程', '调度', '死锁', '信号量',
                    '文件', '目录', '磁盘调度', '页面置换', '分页', '分段']
        
        for kw in keywords:
            # Find keyword that appears at/near start of a logical section
            pattern3 = r'(?:^|(?<=[。；\n]))\s*([^。；]{0,10}' + re.escape(kw) + r'[^。；]{0,20})'
            matches = list(re.finditer(pattern3, text))
            for m in matches:
                candidate = m.group(1).strip()
                if len(candidate) >= 4 and len(candidate) <= 40:
                    sections.append((m.start(), candidate))
        
        # Sort sections by position
        sections.sort(key=lambda x: x[0])
        
        # Deduplicate
        unique_sections = []
        seen_positions = set()
        for pos, title in sections:
            if pos not in seen_positions:
                seen_positions.add(pos)
                # Normalize for dedup
                title_clean = re.sub(r'[^\u4e00-\u9fff\w]', '', title)[:20]
                if title_clean and title_clean not in seen_titles:
                    seen_titles.add(title_clean)
                    unique_sections.append((pos, title))
        
        if len(unique_sections) >= 2:
            # Split page content by detected sections
            for i, (pos, title) in enumerate(unique_sections):
                if i + 1 < len(unique_sections):
                    next_pos = unique_sections[i + 1][0]
                    content = text[pos:next_pos].strip()
                else:
                    content = text[pos:].strip()
                
                # Clean content: remove the title from content if it starts with it
                if content.startswith(title):
                    content = content[len(title):].strip()
                
                # Filter out garbled-only content
                chinese_count = sum(1 for c in content if '\u4e00' <= c <= '\u9fff')
                total_chars = len(content.replace(' ', '').replace('\n', ''))
                
                if chinese_count >= 5 and total_chars >= 10:
                    kps.append({
                        "title": title,
                        "content": content,
                        "tags": [subject],
                        "page": page_num,
                    })
        
        # Strategy 2: If no clear sections found, use the first meaningful sentence as title
        if len(unique_sections) < 2:
            # Find first meaningful sentence
            sentences = re.split(r'(?<=[。；])', text)
            meaningful_sentences = [s.strip() for s in sentences if s.strip() and 
                                    sum(1 for c in s if '\u4e00' <= c <= '\u9fff') >= 3]
            
            if meaningful_sentences:
                first = meaningful_sentences[0]
                # Use first 20-40 chars as title
                title = first[:min(len(first), 40)]
                content = text
                
                chinese_count = sum(1 for c in content if '\u4e00' <= c <= '\u9fff')
                if chinese_count >= 5:
                    kps.append({
                        "title": title,
                        "content": content,
                        "tags": [subject],
                        "page": page_num,
                    })
    
    # Deduplicate by normalized title
    seen = set()
    deduped = []
    for kp in kps:
        key = re.sub(r'[^\u4e00-\u9fff\w]', '', kp['title'])[:30]
        if key not in seen:
            seen.add(key)
            deduped.append(kp)
    
    return deduped


def main():
    pdfs = [
        ("数据结构（总笔记）163Pq.pdf", "数据结构"),
        ("组成原理（总笔记）156Pq.pdf", "计算机组成原理"),
        ("计网（总笔记）101Pq.pdf", "计算机网络"),
    ]
    
    all_kps = []
    total_chars = 0
    
    for pdf_name, subject in pdfs:
        print(f"\n处理: {pdf_name} ({subject})")
        pdf_path = TIKU / pdf_name
        if not pdf_path.exists():
            print(f"  文件不存在，跳过")
            continue
        
        pages_text = extract_all_pages(pdf_path)
        print(f"  提取了 {len(pages_text)} 页的文本")
        
        char_count = sum(len(t) for t in pages_text)
        chinese_count = sum(sum(1 for c in t if '\u4e00' <= c <= '\u9fff') for t in pages_text)
        print(f"  总字符: {char_count}, 中文字符: {chinese_count}")
        total_chars += char_count
        
        raw_path = DATA / f"raw_{subject}.txt"
        with open(raw_path, 'w', encoding='utf-8') as f:
            for i, text in enumerate(pages_text):
                if text.strip():
                    f.write(f"\n=== 第{i+1}页 ===\n")
                    f.write(text)
        print(f"  原始文本已保存至: {raw_path}")
        
        kps = structure_knowledge_points(pages_text, subject)
        print(f"  提取到 {len(kps)} 个知识点")
        all_kps.extend(kps)
    
    print(f"\n{'='*60}")
    print(f"总共提取: {len(all_kps)} 个知识点, {total_chars} 字符")
    
    if all_kps:
        output = DATA / "knowledge_points.jsonl"
        with open(output, 'w', encoding='utf-8') as f:
            for kp in all_kps:
                f.write(json.dumps(kp, ensure_ascii=False) + '\n')
        print(f"知识点已保存至: {output}")
        
        print(f"\n=== 样例知识点 ===")
        for kp in all_kps[:10]:
            print(f"\n  [{kp['tags'][0]}] (第{kp['page']}页) {kp['title'][:50]}")
            print(f"  内容: {kp['content'][:80]}...")


if __name__ == "__main__":
    main()
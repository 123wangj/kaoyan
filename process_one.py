# -*- coding: utf-8 -*-
"""处理单个 PDF"""
import sys
import os
import fitz
import cv2
import numpy as np


def remove_watermarks_from_image(bgr):
    out = bgr.copy()
    h, w = out.shape[:2]
    # 紫色角标 - 颜色 BGR(231,213,225) 浅紫
    # 在四个角都检测
    lower_bgr = np.array([215, 195, 210])
    upper_bgr = np.array([245, 230, 245])
    badge_mask = cv2.inRange(out, lower_bgr, upper_bgr)

    # 检查所有四个角
    for corner_name, (y_slice, x_slice) in [
        ('TL', (slice(0, int(h*0.10)), slice(0, int(w*0.22)))),
        ('TR', (slice(0, int(h*0.10)), slice(int(w*0.78), w))),
        ('BL', (slice(int(h*0.90), h), slice(0, int(w*0.22)))),
        ('BR', (slice(int(h*0.90), h), slice(int(w*0.78), w))),
    ]:
        region_mask = np.zeros_like(badge_mask)
        region_mask[y_slice, x_slice] = 255
        local = cv2.bitwise_and(badge_mask, region_mask)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(local, connectivity=8)
        if n > 1:
            # 找最大连通区域
            best_i = max(range(1, n), key=lambda i: stats[i, cv2.CC_STAT_AREA])
            area = stats[best_i, cv2.CC_STAT_AREA]
            if area > 500:  # 至少要有一定大小
                # 扩展区域以覆盖黑色文字
                x, y, ww, hh = stats[best_i, :4]
                pad = 8
                x0 = max(0, x - pad)
                y0 = max(0, y - pad)
                x1 = min(w, x + ww + pad)
                y1 = min(h, y + hh + pad)
                out[y0:y1, x0:x1] = (255, 255, 255)

    # 背景水印 - 浅灰度 (200-254) + 低色差
    b, g, r = cv2.split(out.astype(np.int16))
    color_diff = (np.maximum(np.maximum(r, g), b) - np.minimum(np.minimum(r, g), b))
    gray = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)
    # 直接定位水印像素 (不连接 - 避免形态学闭运算覆盖文字)
    # 1) 浅灰色水印 (218-254, cd<=8)
    wm_mask_gray = ((gray >= 218) & (gray <= 254) & (color_diff <= 8))
    # 2) 蓝/紫色调水印 (B-R>=5, gray 80-230) - 排除纯黑文字
    wm_mask_blue = ((b - r >= 5) & (gray >= 80) & (gray <= 230))
    wm_mask = wm_mask_gray | wm_mask_blue

    # 找连通区域 (基于原始 mask，不做形态学)
    wm_mask_u8 = (wm_mask.astype(np.uint8)) * 255
    n, labels, stats, _ = cv2.connectedComponentsWithStats(wm_mask_u8, connectivity=8)
    if n > 1:
        for i in range(1, n):
            x, y, ww, hh, area = stats[i]
            if area < 300:  # 跳过太小的噪点
                continue
            # 检查是否在页面中间区域 (避免删除页眉页脚背景)
            cx = x + ww/2
            cy = y + hh/2
            if not (w*0.05 < cx < w*0.95 and h*0.10 < cy < h*0.90):
                continue
            # 移除此区域
            final_mask = (labels == i)
            out[final_mask] = (255, 255, 255)
    return out


def redact_text(page, patterns):
    found = 0
    # 先收集所有匹配区域
    redact_rects = []
    for pat in patterns:
        try:
            for inst in page.search_for(pat):
                redact_rects.append(inst)
                found += 1
        except Exception:
            pass
    # 扩展匹配区域
    extra_rects = []
    for rect in redact_rects:
        x0, y0, x1, y1 = rect
        h = y1 - y0
        w = x1 - x0
        expanded = fitz.Rect(x0 - w*0.4, y0 - h*0.3, x1 + w*0.4, y1 + h*0.3)
        extra_rects.append(expanded)
    # 应用 redaction
    for rect in extra_rects:
        try:
            page.add_redact_annot(rect, text="", fill=(1, 1, 1))
        except Exception:
            pass
    return found, len(extra_rects)


def process_pdf(src, dst, max_pages=None):
    print(f'Opening: {src}', flush=True)
    src_doc = fitz.open(src)
    total = min(max_pages, src_doc.page_count) if max_pages else src_doc.page_count
    print(f'  Total pages: {src_doc.page_count}, processing: {total}', flush=True)
    patterns = ['里昂学长', '@里昂学长', '25考研版', '25 考研版', '里昂学长小伙伴']

    # 整页栅格化方法: 创建新 PDF, 每页为清理后的图像
    out_doc = fitz.open()
    matrix = fitz.Matrix(2.0, 2.0)  # 2.0x 足够清晰

    for i, src_page in enumerate(src_doc):
        if i >= total:
            break
        if i % 10 == 0:
            print(f'  Page {i+1}/{total}', flush=True)
        try:
            # 文字水印: 先 redact
            _, n_rects = redact_text(src_page, patterns)
            if i == 0:
                for pat in ['（', '）']:
                    for inst in src_page.search_for(pat):
                        try:
                            src_page.add_redact_annot(inst, text="", fill=(1, 1, 1))
                        except Exception:
                            pass
            try:
                src_page.apply_redactions()
            except Exception:
                pass
            # 渲染为高分辨率图像
            pix = src_page.get_pixmap(matrix=matrix, alpha=False)
            w, h = pix.width, pix.height
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(h, w, 3)
            bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
            # 移除水印
            cleaned = remove_watermarks_from_image(bgr)
            # 编码为 JPEG
            success, buf = cv2.imencode('.jpg', cleaned, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not success:
                # 失败时复制原页
                out_doc.insert_pdf(src_doc, from_page=i, to_page=i)
                continue
            # 创建新页面 (使用源页面的实际尺寸, 因为 matrix=2.5 会放大 2.5 倍)
            actual_w = src_page.rect.width
            actual_h = src_page.rect.height
            new_page = out_doc.new_page(width=actual_w, height=actual_h)
            new_pix = fitz.Pixmap(buf.tobytes())
            # 缩放图像: 2.5x, 所以图像尺寸 / 2.5
            img_w = new_pix.width / matrix.a
            img_h = new_pix.height / matrix.d
            # 显示尺寸: 填满页面
            new_page.insert_image(fitz.Rect(0, 0, actual_w, actual_h), pixmap=new_pix)
        except Exception as e:
            print(f'  Page {i+1} error: {e}', flush=True)
            # 出错时复制原页
            try:
                out_doc.insert_pdf(src_doc, from_page=i, to_page=i)
            except Exception:
                pass

    src_doc.close()
    print(f'  Saving to: {dst}', flush=True)
    try:
        out_doc.save(dst, garbage=2, deflate=True)
        print(f'  Saved!', flush=True)
    except Exception as e:
        print(f'  Save error: {e}', flush=True)
        with open(dst, 'wb') as f:
            f.write(out_doc.tobytes())
    out_doc.close()
    sz = os.path.getsize(dst) / 1024 / 1024
    print(f'  Output size: {sz:.2f} MB', flush=True)


if __name__ == '__main__':
    src_dir = r'c:\Users\wang\Desktop\考研学习\tiku'
    dst_dir = r'c:\Users\wang\Desktop\考研学习\cleaned'
    os.makedirs(dst_dir, exist_ok=True)

    # 处理指定的 PDF
    target = sys.argv[1] if len(sys.argv) > 1 else None
    pdfs = [
        '里昂学长408考研操作系统笔记（定稿）.pdf',
        '里昂学长408考研计算机组成原理笔记（定稿）.pdf',
        '里昂学长408考研计算机网络笔记（定稿）（公众号：里昂学长的小伙伴们）.pdf',
        '408数据结构笔记(已定稿)（公众号：里昂学长的小伙伴们）.pdf',
        '组成原理（总笔记）156Pq.pdf',
        '操作系统（总笔记）159Pq.pdf',
        '数据结构（总笔记）163Pq.pdf',
        '计网（总笔记）101Pq.pdf',
    ]
    for fname in pdfs:
        if target and target not in fname:
            continue
        src = os.path.join(src_dir, fname)
        dst = os.path.join(dst_dir, fname)
        try:
            process_pdf(src, dst)
        except Exception as e:
            print(f'Error: {e}', flush=True)
    print('All done!')

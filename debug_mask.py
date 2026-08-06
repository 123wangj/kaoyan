import fitz
doc = fitz.open(r'cleaned\里昂学长408考研计算机组成原理笔记（定稿）.pdf')
for pidx in [0, 50, 100, 200, 322]:
    page = doc[pidx]
    mat = fitz.Matrix(1.5, 1.5)
    pix = page.get_pixmap(matrix=mat)
    pix.save(f'C:\\Temp\\dbg\\q85_{pidx}.png')
doc.close()
print('done')

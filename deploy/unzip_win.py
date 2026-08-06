#!/usr/bin/env python3
"""解压 Windows 风格 zip(反斜杠路径)到 /opt/kaoyan-ai"""
import os
import sys
import zipfile

zip_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/kaoyan-deploy-bundle.zip"
target_dir = sys.argv[2] if len(sys.argv) > 2 else "/opt/kaoyan-ai"

os.makedirs(target_dir, exist_ok=True)
count = 0
with zipfile.ZipFile(zip_path) as z:
    for name in z.namelist():
        # Windows zip 用反斜杠,统一转正斜杠
        fixed = name.replace("\\", "/")
        if not fixed:
            continue
        out_path = os.path.join(target_dir, fixed)
        if fixed.endswith("/"):
            os.makedirs(out_path, exist_ok=True)
            continue
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with z.open(name) as src, open(out_path, "wb") as dst:
            dst.write(src.read())
        count += 1

print(f"OK: {count} files extracted to {target_dir}")

# -*- coding: utf-8 -*-
"""生成云端上传用 zip 包:
  - 狼吃羊棋_完整版_1_程序.zip    (程序+值表, ~1GB)
  - 狼吃羊棋_完整版_2_距离表.zip  (精确距离表, 3.5GB)
  - 狼吃羊棋_精简版.zip           (程序+值表, ~1GB)
大 .zst 文件用 STORED(已压缩),其余 DEFLATED;均流式写入,不占内存。
"""
import os
import shutil
import zipfile

ROOT = r"D:\狼吃羊棋\软件包"
FULL = os.path.join(ROOT, "完整版", "WolfSheepAI")
LITE = os.path.join(ROOT, "精简版", "WolfSheepAI")
OUT = os.path.join(ROOT, "上传")


def add_tree(z, base, store_names=(), skip=()):
    """把 base 目录按原结构写入 zip;store_names 中的相对路径用 STORED。
    跳过已解压的大表(.npy/.dat)、.tmp 残留与 skip 指定文件。"""
    for root, dirs, files in os.walk(base):
        for fn in sorted(files):
            if fn.endswith(".tmp") or fn in skip:
                continue
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, base).replace("\\", "/")
            store = rel in store_names
            zi = zipfile.ZipInfo(rel)
            zi.compress_type = zipfile.ZIP_STORED if store else zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            big = os.path.getsize(p) > (1 << 31)
            with z.open(zi, "w", force_zip64=big) as out, open(p, "rb") as f:
                shutil.copyfileobj(f, out)
            print(f"  {'[存]' if store else '[压]'} {rel}")


def build():
    os.makedirs(OUT, exist_ok=True)

    # 1) 程序+值表(完整版的一半)
    p = os.path.join(OUT, "狼吃羊棋_完整版_1_程序.zip")
    if os.path.exists(p):
        os.remove(p)
    print("生成 完整版_1_程序.zip ...")
    with zipfile.ZipFile(p, "w", allowZip64=True) as z:
        add_tree(z, FULL,
                 store_names={"tt/full_packed.npy.zst"},
                 skip={"full_packed.npy", "full_dist.dat", "full_dist.dat.zst"})
        z.write(os.path.join(os.path.dirname(FULL), "使用说明.txt"),
                "使用说明.txt")
    print("  完成", round(os.path.getsize(p) / 1e9, 2), "GB")

    # 2) 距离表(完整版的另一半, 3.5GB 需 zip64)
    p = os.path.join(OUT, "狼吃羊棋_完整版_2_距离表.zip")
    if os.path.exists(p):
        os.remove(p)
    print("生成 完整版_2_距离表.zip ...")
    with zipfile.ZipFile(p, "w", allowZip64=True) as z:
        zi = zipfile.ZipInfo("tt/full_dist.dat.zst")
        zi.compress_type = zipfile.ZIP_STORED
        zi.external_attr = 0o644 << 16
        with z.open(zi, "w", force_zip64=True) as out, \
                open(os.path.join(FULL, "tt", "full_dist.dat.zst"), "rb") as f:
            shutil.copyfileobj(f, out)
    print("  完成", round(os.path.getsize(p) / 1e9, 2), "GB")

    # 3) 精简版(单文件)
    p = os.path.join(OUT, "狼吃羊棋_精简版.zip")
    if os.path.exists(p):
        os.remove(p)
    print("生成 精简版.zip ...")
    with zipfile.ZipFile(p, "w", allowZip64=True) as z:
        add_tree(z, LITE,
                 store_names={"tt/full_packed.npy.zst"},
                 skip={"full_packed.npy", "full_dist.dat", "full_dist.dat.zst"})
        z.write(os.path.join(os.path.dirname(LITE), "使用说明.txt"),
                "使用说明.txt")
    print("  完成", round(os.path.getsize(p) / 1e9, 2), "GB")
    print("全部生成完毕 ->", OUT)


if __name__ == "__main__":
    build()

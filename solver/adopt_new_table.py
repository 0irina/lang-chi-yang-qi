# -*- coding: utf-8 -*-
"""新规则破解表完成后的检查与换表(人工确认后运行)。

用法:
  python solver\\adopt_new_table.py check    # 只读检查 tt_new,报告关键值,不动任何文件
  python solver\\adopt_new_table.py swap     # 备份旧表 → 换入新表 → 重压 .zst → 清理

swap 之后还需(手工执行):
  python -u solver\\zip_pkg.py               # 重建三个上传 zip(距离表这次也会变)
"""
import os
import shutil
import sys
import time

SOL = r"D:\狼吃羊棋\solver"
TT = os.path.join(SOL, "tt")
NEW = os.path.join(SOL, "tt_new")
PKG_FULL_TT = r"D:\狼吃羊棋\软件包\完整版\WolfSheepAI\tt"
PKG_LITE_TT = r"D:\狼吃羊棋\软件包\精简版\WolfSheepAI\tt"
DIST_TT = r"D:\狼吃羊棋\dist\WolfSheepAI\tt"


def check():
    flag = os.path.join(NEW, "full_done.flag")
    if not os.path.exists(flag):
        print("tt_new 尚无 full_done.flag —— 破解未完成或复核未通过,拒绝操作")
        return 1
    sys.path.insert(0, SOL)
    import endgame
    endgame.load_tables(NEW)
    from rules import (INIT_WOLVES, INIT_SHEEP, WOLF, SHEEP,
                       WIN_NAMES, pos_name)
    from engine import Engine

    v = endgame.lookup(INIT_WOLVES, INIT_SHEEP, WOLF)
    d = endgame.lookup_dist(INIT_WOLVES, INIT_SHEEP, WOLF)
    print(f"初始局面: {WIN_NAMES.get(v)}  距离: {d}")
    eng = Engine()
    mv, info = eng.best_move(INIT_WOLVES, INIT_SHEEP, WOLF, ply_budget=150)
    print(f"初始最佳: {pos_name(mv[0])}→{pos_name(mv[1])}"
          f"{' 吃' if mv[2] else ''}  值={WIN_NAMES.get(info['value'])}"
          f"  距={info['dist']}")

    W = (1 << 1) | (1 << 2) | (1 << 3)
    S3 = (1 << 11) | (1 << 20) | (1 << 24)
    print(f"k=3 狼回合: {WIN_NAMES.get(endgame.lookup(W, S3, WOLF))} (应=狼胜)")
    print(f"k=3 羊回合: {WIN_NAMES.get(endgame.lookup(W, S3, SHEEP))} (应=狼胜)")
    W2 = (1 << 0) | (1 << 1) | (1 << 5)
    S4 = (1 << 2) | (1 << 6) | (1 << 10) | (1 << 11)
    print(f"k=4 围死狼: {WIN_NAMES.get(endgame.lookup(W2, S4, WOLF))} (应=羊胜)")
    return 0


def swap():
    sys.path.insert(0, SOL)
    flag = os.path.join(NEW, "full_done.flag")
    assert os.path.exists(flag), "tt_new 没有 full_done.flag,拒绝换表"
    for n in ("full_packed.npy", "full_dist.dat"):
        assert os.path.exists(os.path.join(NEW, n)), f"tt_new 缺 {n}"

    # 1) 旧表改名备份(同卷改名,秒级)
    for n in ("full_packed.npy", "full_dist.dat"):
        src = os.path.join(TT, n)
        if os.path.exists(src):
            bak = src + ".old_rule"
            if os.path.exists(bak):
                os.remove(bak)
            os.replace(src, bak)
    # 2) 换入新表
    for n in ("full_packed.npy", "full_dist.dat", "full_done.flag"):
        shutil.copy2(os.path.join(NEW, n), os.path.join(TT, n))
    print("新表已换入 solver\\tt(旧表备份为 *.old_rule)")

    # 3) dist\ 里上次自检遗留的旧表硬链接 → 指向新表
    if os.path.isdir(DIST_TT):
        for n in os.listdir(DIST_TT):
            os.remove(os.path.join(DIST_TT, n))
    else:
        os.makedirs(DIST_TT)
    for n in ("full_packed.npy", "full_dist.dat", "full_done.flag"):
        try:
            os.link(os.path.join(TT, n), os.path.join(DIST_TT, n))
        except OSError:
            shutil.copy2(os.path.join(TT, n), os.path.join(DIST_TT, n))
    print("dist 自检表已更新")

    # 4) 重新压缩 .zst(覆盖软件包里的旧 .zst)
    import tabpack
    for n in ("full_packed.npy", "full_dist.dat"):
        t0 = time.time()
        tabpack.pack(os.path.join(TT, n), os.path.join(PKG_FULL_TT, n + ".zst"),
                     level=9)
        print(f"  压缩 {n} → .zst 用时 {time.time()-t0:.0f}s")
    shutil.copy2(os.path.join(PKG_FULL_TT, "full_packed.npy.zst"),
                 os.path.join(PKG_LITE_TT, "full_packed.npy.zst"))
    print("软件包 .zst 已更新")

    # 5) 清理 tt_new 大文件(队列 77GB 等,约释放 115GB)
    shutil.rmtree(NEW, ignore_errors=True)
    print("tt_new 已清理")
    print("下一步: python -u solver\\zip_pkg.py 重建上传 zip")
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    sys.exit(check() if mode == "check" else swap())

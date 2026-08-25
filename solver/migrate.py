# -*- coding: utf-8 -*-
"""破解进度迁移工具(笔记本 -> 台式机)

用法:
  源机器(先停止破解进程,最好在日志刚出现"[进度]"行之后停止):
      python solver/migrate.py pack D:\迁移包
      然后把"迁移包"文件夹 + solver 代码文件夹拷到台式机
  目标机器(已装好 Python + numpy + numba):
      python solver/migrate.py unpack D:\迁移包
      python solver/endgame_full.py 15 --resume

说明:
  * 破解表的检查点(full_packed.npy,9.6GB)与距离表(full_dist.dat,19GB)整体拷贝;
  * 队列只拷贝未处理的部分(通常 <2GB),目标机器重建 77GB 稀疏文件(瞬间完成);
  * 打包总量约 31GB,比整目录拷贝(106GB)小很多。
"""
import json
import os
import shutil
import sys

import numpy as np


def tt_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "tt")


def pack(outdir):
    tt = tt_dir()
    os.makedirs(outdir, exist_ok=True)
    tab_path = os.path.join(tt, "full_packed.npy")
    meta_path = os.path.join(tt, "full_meta.npy")
    queue_path = os.path.join(tt, "full_queue.dat")
    dist_path = os.path.join(tt, "full_dist.dat")
    for p in (tab_path, meta_path, queue_path, dist_path):
        if not os.path.exists(p):
            print(f"缺少文件 {p},请确认破解已运行过至少一个检查点")
            raise SystemExit(1)

    tab = np.load(tab_path, mmap_mode="r")
    N = len(tab)
    meta = np.load(meta_path)
    head, tail = int(meta[0]), int(meta[1])
    print(f"表大小 N={N:,}  队列头={head:,}  队列尾={tail:,}  待处理={tail-head:,}")

    # 1) 破解表(9.6GB,全量有效数据)
    print("复制破解表 full_packed.npy ...")
    shutil.copy(tab_path, os.path.join(outdir, "full_packed.npy"))
    # 2) 队列待处理段(兼作距离表索引)
    print("提取队列待处理段 ...")
    q = np.memmap(queue_path, dtype=np.uint64, mode="r", shape=(N,))
    pending = np.array(q[head:tail])
    np.save(os.path.join(outdir, "full_queue_pending.npy"), pending)
    # 3) 距离表:只提取待处理状态的值(稀疏,不复制 19GB 空壳)
    print("提取距离表有效部分 ...")
    dist = np.memmap(dist_path, dtype=np.uint16, mode="r", shape=(N,))
    vals = np.array(dist[pending])
    np.save(os.path.join(outdir, "full_dist_pending.npy"), vals)
    # 4) 元信息
    with open(os.path.join(outdir, "migrate_meta.json"), "w") as f:
        json.dump(dict(N=N, head=0, tail=len(pending)), f)
    total = os.path.getsize(os.path.join(outdir, "full_packed.npy")) \
        + os.path.getsize(os.path.join(outdir, "full_queue_pending.npy")) \
        + os.path.getsize(os.path.join(outdir, "full_dist_pending.npy"))
    print(f"打包完成 -> {outdir} (共 {total/1e9:.1f}GB)")
    print(f"待拷贝: {outdir} 文件夹 + solver 代码文件夹(rules/index/endgame/endgame_full.py 等)")


def unpack(indir):
    tt = tt_dir()
    os.makedirs(tt, exist_ok=True)
    with open(os.path.join(indir, "migrate_meta.json")) as f:
        meta = json.load(f)
    N = meta["N"]
    head, tail = meta["head"], meta["tail"]

    print("还原破解表 ...")
    shutil.copy(os.path.join(indir, "full_packed.npy"),
                os.path.join(tt, "full_packed.npy"))
    print("重建距离表(稀疏) ...")
    dist = np.memmap(os.path.join(tt, "full_dist.dat"), dtype=np.uint16,
                     mode="w+", shape=(N,))
    pending = np.load(os.path.join(indir, "full_queue_pending.npy"))
    vals = np.load(os.path.join(indir, "full_dist_pending.npy"))
    dist[pending] = vals
    dist.flush()
    print("重建队列文件(稀疏) ...")
    q = np.memmap(os.path.join(tt, "full_queue.dat"), dtype=np.uint64,
                  mode="w+", shape=(N,))
    q[0:len(pending)] = pending
    q.flush()
    np.save(os.path.join(tt, "full_meta.npy"),
            np.array([head, tail], dtype=np.int64))
    print(f"还原完成。现在可以运行: python solver/endgame_full.py 15 --resume")


def clean():
    """破解完成后清理临时文件(释放约 77GB)。仅在 full_done.flag 存在时执行。"""
    tt = tt_dir()
    flag = os.path.join(tt, "full_done.flag")
    if not os.path.exists(flag):
        print("未检测到完成标志 full_done.flag,破解尚未完成,拒绝清理")
        raise SystemExit(1)
    freed = 0
    for name in ("full_queue.dat", "full_meta.npy", "full_packed_tmp.npy",
                 "full_live.dat"):
        p = os.path.join(tt, name)
        if os.path.exists(p):
            freed += os.path.getsize(p)
            os.remove(p)
            print(f"已删除 {name} ({os.path.getsize(p)/1e9:.1f}GB)")
    print(f"清理完成,释放约 {freed/1e9:.1f}GB。保留 full_packed.npy 与 full_dist.dat")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    cmd = sys.argv[1]
    if cmd == "pack" and len(sys.argv) >= 3:
        pack(sys.argv[2])
    elif cmd == "unpack" and len(sys.argv) >= 3:
        unpack(sys.argv[2])
    elif cmd == "clean":
        clean()
    else:
        print(__doc__)
        raise SystemExit(1)

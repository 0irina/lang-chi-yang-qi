# -*- coding: utf-8 -*-
"""从顺序版存档快照到独立目录,供并行版续跑(顺序版原存档不动)"""
import json
import os
import shutil
import sys

import numpy as np

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tt")
DST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tt_par_full")


def main():
    os.makedirs(DST, exist_ok=True)
    tab_path = os.path.join(SRC, "full_packed.npy")
    meta_path = os.path.join(SRC, "full_meta.npy")
    queue_path = os.path.join(SRC, "full_queue.dat")
    dist_path = os.path.join(SRC, "full_dist.dat")

    tab = np.load(tab_path, mmap_mode="r")
    N = len(tab)
    meta = np.load(meta_path)
    head, tail = int(meta[0]), int(meta[1])
    print(f"快照: 表 N={N:,} 头={head:,} 尾={tail:,} 待处理={tail-head:,}")

    shutil.copy(tab_path, os.path.join(DST, "full_packed.npy"))
    q = np.memmap(queue_path, dtype=np.uint64, mode="r", shape=(N,))
    pending = np.array(q[head:tail])
    d = np.memmap(dist_path, dtype=np.uint16, mode="r", shape=(N,))
    vals = np.array(d[pending])
    q2 = np.memmap(os.path.join(DST, "full_queue.dat"), dtype=np.uint64,
                   mode="w+", shape=(N,))
    q2[0:len(pending)] = pending
    q2.flush()
    d2 = np.memmap(os.path.join(DST, "full_dist.dat"), dtype=np.uint16,
                   mode="w+", shape=(N,))
    d2[pending] = vals
    d2.flush()
    np.save(os.path.join(DST, "full_meta.npy"), np.array([0, len(pending)], dtype=np.int64))
    print(f"快照完成 -> {DST}")


if __name__ == "__main__":
    main()

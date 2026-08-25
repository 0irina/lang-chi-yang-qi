# -*- coding: utf-8 -*-
"""预热 dist_check 的 numba 内核(强制编译进缓存,不用真实 tt 数据)。

在 dist_pass 运行期间调用是安全的:只用小 dummy 数组,不读 full_dist.dat。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from index import (WOLF_MASKS, FREECELLS, FREELIST, CTAB_FLAT, C22K, SHEEP_OFF,
                   M_CANON, WR_OF_DENSE, MIRROR_WR, MIRROR_CELL, WDEN,
                   PLACEOFF_C)
from endgame_full import NEIGH
import dist_check

N_DUMMY = 8_000_000


def main():
    # ---- Phase A kernel ----
    value5 = np.zeros(N_DUMMY, dtype=np.uint8)
    dist5 = np.zeros(N_DUMMY, dtype=np.uint8)
    dist_mm = np.zeros(N_DUMMY, dtype=np.uint16)
    r = dist_check._check_k35(
        value5, dist5, dist_mm, PLACEOFF_C, C22K, WOLF_MASKS, FREECELLS,
        CTAB_FLAT, FREELIST, WDEN, MIRROR_WR, MIRROR_CELL, SHEEP_OFF, 0, 1)
    print("A kernel compiled, dummy result mism=", r[0])

    # ---- Phase B kernel ----
    tab = np.zeros(N_DUMMY, dtype=np.uint8)
    dist = np.zeros(N_DUMMY, dtype=np.uint16)
    idxs = np.array([0], dtype=np.uint64)
    r = dist_check._check_sample(
        tab, dist, idxs, PLACEOFF_C, C22K, WOLF_MASKS, WR_OF_DENSE, FREECELLS,
        CTAB_FLAT, FREELIST, WDEN, MIRROR_WR, MIRROR_CELL, NEIGH, 15)
    print("B kernel compiled, dummy result mism=", r[0])
    print("WARMUP OK")


if __name__ == "__main__":
    main()

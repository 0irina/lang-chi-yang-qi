# -*- coding: utf-8 -*-
"""复现 _dist_seed 在 k=14 层的崩溃(faulthandler 定位)"""
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dist_pass as DP
from index import (PLACEOFF_C, C22K, WOLF_MASKS, WR_OF_DENSE, FREECELLS,
                   FREELIST, CTAB_FLAT, MIRROR_WR, MIRROR_CELL)
from endgame_full import full_size, NEIGH

N = full_size(15)
print("加载表...", flush=True)
tab = np.load(r'D:\狼吃羊棋\solver\tt\full_packed.npy')
dist = np.memmap(r'D:\狼吃羊棋\solver\tt\full_dist.dat', dtype=np.uint16,
                 mode='r+', shape=(N,))
queue = np.memmap(r'D:\狼吃羊棋\solver\tt\full_distq.dat', dtype=np.uint64,
                  mode='w+', shape=(N,))
print("从 ki=11(k=14)开始扫描...", flush=True)
t0 = time.time()
tail = DP._dist_seed(15, tab, dist, queue, PLACEOFF_C, C22K, WOLF_MASKS,
                     WR_OF_DENSE, FREECELLS, FREELIST, CTAB_FLAT, MIRROR_WR,
                     MIRROR_CELL, NEIGH, start_ki=11)
print(f"扫描完成 tail={tail} 用时={time.time()-t0:.1f}s", flush=True)

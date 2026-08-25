# -*- coding: utf-8 -*-
"""量化并行版 dist 与精确 dist 的误差分布"""
import random
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from index import (C22K, PLACEOFF_C, WDEN, rank_wolf_mask, canon_state,
                   rank_sheep_mask, PLACEOFF)

par_tab = np.load(r'D:\狼吃羊棋\solver\tt_par_full\full_packed.npy')
par_dist = np.memmap(r'D:\狼吃羊棋\solver\tt_par_full\full_dist.dat',
                     dtype=np.uint16, mode='r', shape=(len(par_tab),))
ref = np.load(r'D:\狼吃羊棋\solver\tt\tt_3_5.npy')
ref_dist = np.load(r'D:\狼吃羊棋\solver\tt\dist_3_5.npy')

rng = random.Random(999)
errs = []
over = under = 0
n = 300000
for i in range(n):
    cells = rng.sample(range(25), 3)
    W = sum(1 << p for p in cells)
    k = rng.randint(3, 5)
    free = [p for p in range(25) if not ((W >> p) & 1)]
    S = sum(1 << p for p in rng.sample(free, k))
    turn = rng.randint(0, 1)
    wr = rank_wolf_mask(W)
    sr = rank_sheep_mask(wr, S)
    ki = k - 3
    idx1 = (int(PLACEOFF[ki]) + wr * int(C22K[ki]) + sr) * 2 + turn
    v1 = int(ref[idx1])
    if v1 not in (1, 2):
        continue
    d1 = int(ref_dist[idx1])
    cwr, cs = canon_state(W, S)
    sr2 = rank_sheep_mask(cwr, cs)
    idx2 = (int(PLACEOFF_C[ki]) + int(WDEN[cwr]) * int(C22K[ki]) + sr2) * 2 + turn
    d2 = int(par_dist[idx2])
    e = d2 - d1
    if e != 0:
        errs.append(e)
        if e > 0:
            over += 1
        else:
            under += 1
errs = np.array(errs)
print(f"抽样 {n}(胜/负局面): dist 不一致 {len(errs)} ({len(errs)/n*100:.1f}%)")
if len(errs):
    print(f"误差统计: 均值 {errs.mean():+.2f}  中位数 {np.median(errs):+.0f}  "
          f"最大偏大 {errs.max():+d}  最大偏小 {errs.min():+d}")
    print(f"偏大 {over} ({over/len(errs)*100:.0f}%)  偏小 {under} ({under/len(errs)*100:.0f}%)")
    print(f"误差绝对值分布: |e|<=1: {(np.abs(errs)<=1).sum()/len(errs)*100:.0f}%  "
          f"<=2: {(np.abs(errs)<=2).sum()/len(errs)*100:.0f}%  "
          f"<=5: {(np.abs(errs)<=5).sum()/len(errs)*100:.0f}%")

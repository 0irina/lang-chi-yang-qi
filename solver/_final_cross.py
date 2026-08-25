# -*- coding: utf-8 -*-
"""最终表 vs 已验证 k≤5 全空间表:随机抽样交叉对拍(胜负值 + 距离)"""
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


def par_lookup(w, s, turn):
    cwr, cs = canon_state(w, s)
    k = s.bit_count()
    sr = rank_sheep_mask(cwr, cs)
    ki = k - 3
    idx = (int(PLACEOFF_C[ki]) + int(WDEN[cwr]) * int(C22K[ki]) + sr) * 2 + turn
    return int(par_tab[idx] & 3), int(par_dist[idx])


def ref_lookup(w, s, turn):
    wr = rank_wolf_mask(w)
    k = s.bit_count()
    sr = rank_sheep_mask(wr, s)
    ki = k - 3
    idx = (int(PLACEOFF[ki]) + wr * int(C22K[ki]) + sr) * 2 + turn
    return int(ref[idx]), int(ref_dist[idx])


rng = random.Random(20240821)
bad_v = bad_d = 0
n = 500000
for i in range(n):
    cells = rng.sample(range(25), 3)
    W = sum(1 << p for p in cells)
    k = rng.randint(3, 5)
    free = [p for p in range(25) if not ((W >> p) & 1)]
    S = sum(1 << p for p in rng.sample(free, k))
    turn = rng.randint(0, 1)
    v1, d1 = ref_lookup(W, S, turn)
    v2, d2 = par_lookup(W, S, turn)
    if v1 != v2:
        bad_v += 1
    if v1 == v2 and v1 in (1, 2) and d1 != d2:
        bad_d += 1
print(f"抽样 {n}: 胜负不一致 {bad_v}, 距离不一致 {bad_d}")
print("PASS" if bad_v == 0 else "FAIL")

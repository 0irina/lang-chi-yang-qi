# -*- coding: utf-8 -*-
"""并行版 k≤5 表 vs 已验证全空间表:随机抽样交叉对拍(仅胜负值)"""
import random
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from index import (C22K, PLACEOFF_C, WDEN, rank_wolf_mask, canon_state,
                   rank_sheep_mask, PLACEOFF, MIRROR_WR, MIRROR_CELL)

par_tab = np.load(r'D:\狼吃羊棋\solver\tt_par\full_packed.npy')
ref = np.load(r'D:\狼吃羊棋\solver\tt\tt_3_5.npy')


def par_lookup(w, s, turn):
    cwr, cs = canon_state(w, s)
    k = s.bit_count()
    sr = rank_sheep_mask(cwr, cs)
    ki = k - 3
    idx = (int(PLACEOFF_C[ki]) + int(WDEN[cwr]) * int(C22K[ki]) + sr) * 2 + turn
    return int(par_tab[idx] & 3)


def ref_lookup(w, s, turn):
    wr = rank_wolf_mask(w)
    k = s.bit_count()
    sr = rank_sheep_mask(wr, s)
    ki = k - 3
    idx = (int(PLACEOFF[ki]) + wr * int(C22K[ki]) + sr) * 2 + turn
    return int(ref[idx])


rng = random.Random(777)
bad = 0
n = 300000
for i in range(n):
    cells = rng.sample(range(25), 3)
    W = sum(1 << p for p in cells)
    k = rng.randint(3, 5)
    free = [p for p in range(25) if not ((W >> p) & 1)]
    S = sum(1 << p for p in rng.sample(free, k))
    turn = rng.randint(0, 1)
    v1 = ref_lookup(W, S, turn)
    v2 = par_lookup(W, S, turn)
    if v1 != v2:
        bad += 1
        if bad <= 5:
            print(f"不一致: W={W} S={S} t={turn} 顺序={v1} 并行={v2}")
print(f"抽样 {n}: 不一致 {bad}")
print("PASS" if bad == 0 else "FAIL")

# -*- coding: utf-8 -*-
"""破解完成后:全表 vs k<=5 全空间表 交叉抽样验证"""
import random
import numpy as np
import endgame
from index import (C22K, PLACEOFF_C, WDEN, MIRROR_WR, MIRROR_CELL,
                   rank_wolf_mask, canon_state, rank_sheep_mask)

endgame.load_tables()
if endgame._FULL is None:
    print("未找到全破解表,先运行 endgame_full.py 15")
    raise SystemExit(1)
tab = endgame._FULL
dist_mm = endgame._FULL_DIST


def full_lookup(w, s, turn):
    cwr, cs = canon_state(w, s)
    k = s.bit_count()
    sr = rank_sheep_mask(cwr, cs)
    ki = k - 3
    idx = (int(PLACEOFF_C[ki]) + int(WDEN[cwr]) * int(C22K[ki]) + sr) * 2 + turn
    return int(tab[idx] & 3), int(dist_mm[idx]) if dist_mm is not None else -1


# 用 k<=5 全空间表(tt_3_5.npy)做对照:直接按非规范索引读
ref = np.load(r"solver\tt\tt_3_5.npy")
ref_dist = np.load(r"solver\tt\dist_3_5.npy")


def ref_lookup(w, s, turn):
    from index import PLACEOFF, rank_sheep_mask
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
    v2, d2 = full_lookup(W, S, turn)
    if v1 != v2:
        bad_v += 1
        if bad_v <= 5:
            print(f"胜负不一致: W={W} S={S} t={turn} ref={v1} full={v2}")
    if v1 == v2 and v1 in (1, 2) and d1 != d2:
        bad_d += 1
        if bad_d <= 5:
            print(f"距离不一致: W={W} S={S} t={turn} ref={d1} full={d2}")
print(f"抽样 {n}: 胜负不一致 {bad_v}, 距离不一致 {bad_d}")
print("PASS" if bad_v == 0 and bad_d == 0 else "FAIL")

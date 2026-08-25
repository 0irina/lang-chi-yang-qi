# -*- coding: utf-8 -*-
"""诊断 dist_check 阶段 A 发现的 24 个 k=4 狼回合 距离1vs0 的不匹配。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import rules
from rules import WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW
from index import (WOLF_MASKS, FREECELLS, FREELIST, CTAB_FLAT, C22K, SHEEP_OFF,
                   M_CANON, WR_OF_DENSE, MIRROR_WR, MIRROR_CELL, WDEN,
                   PLACEOFF_C)
import endgame_full as EF
from endgame_full import _encode_c, _unrank_sheep, _has_wolf_move, _decode_c, NEIGH

TT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tt")
NW = 2300

CASES = [(139, 1), (150, 9), (237, 74), (250, 370), (636, 4841)]


def cell_name(c):
    return f"({c // 5 + 1},{c % 5 + 1})"


def main():
    value5 = np.load(os.path.join(TT, "tt_3_5.npy"), mmap_mode="r")
    dist5 = np.load(os.path.join(TT, "dist_3_5.npy"), mmap_mode="r")
    tab = np.load(os.path.join(TT, "full_packed.npy"), mmap_mode="r")
    N = EF.full_size(15)
    dist = np.memmap(os.path.join(TT, "full_dist.dat"), dtype=np.uint16,
                     mode="r", shape=(N,))
    for wr, sr in CASES:
        ki = 1  # k=4
        i5 = (int(SHEEP_OFF[ki]) * NW + wr * int(C22K[ki]) + sr) * 2
        rv = int(value5[i5])
        rd = int(dist5[i5])
        W = WOLF_MASKS[wr]
        S = _unrank_sheep(wr, sr, 4, FREECELLS, CTAB_FLAT)
        cidx = _encode_c(W, S, WOLF, PLACEOFF_C, C22K, CTAB_FLAT, FREELIST,
                         WDEN, MIRROR_WR, MIRROR_CELL)
        cv = int(tab[cidx] & 3)
        cd = int(dist[cidx])
        has = _has_wolf_move(W, S, NEIGH)
        Wd, Sd, td, kd = _decode_c(cidx, PLACEOFF_C, C22K, WOLF_MASKS,
                                   WR_OF_DENSE, FREECELLS, CTAB_FLAT)
        wc = [cell_name(c) for c in range(25) if (W >> c) & 1]
        sc = [cell_name(c) for c in range(25) if (S >> c) & 1]
        print(f"wr={wr} sr={sr}: ref_v={rv} ref_d={rd} canon_v={cv} "
              f"canon_d={cd} has_wolf_move={has}")
        print(f"   狼={wc} 羊={sc}")
        print(f"   规范槽解码: 狼={[cell_name(c) for c in range(25) if (Wd>>c)&1]} "
              f"羊={[cell_name(c) for c in range(25) if (Sd>>c)&1]}")
        print()


if __name__ == "__main__":
    main()

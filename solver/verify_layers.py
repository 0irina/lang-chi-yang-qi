# -*- coding: utf-8 -*-
"""分层并行复核:13 个进程各自独立复核一个羊数层,互不干扰

用法:python solver/verify_layers.py <表目录> [--workers 13]
每层逻辑与 endgame_full._verify_full 的层循环体完全一致。
"""
import os
import sys
import time
from multiprocessing import Pool

import numpy as np
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rules
from rules import WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, ALL_MASK
from index import (WOLF_MASKS, FREECELLS, FREELIST, CTAB_FLAT, C22K, PLACEOFF_C,
                   M_CANON, WR_OF_DENSE, MIRROR_WR, MIRROR_CELL, WDEN)
import endgame_full as EF
from endgame_full import (_encode_c, _unrank_sheep, _wolf_succs, _sheep_succs,
                          _slot_canonical, NEIGH)


@njit(cache=True)
def _verify_one_layer(k, tab, PLACEOFF_C, C22K, WOLF_MASKS, WR_OF_DENSE,
                      FREECELLS, FREELIST, CTAB_FLAT, WDEN, MIRROR_WR,
                      MIRROR_CELL, NEIGH):
    bad = 0
    Wout = np.empty(64, dtype=np.int64)
    Sout = np.empty(64, dtype=np.int64)
    capout = np.empty(64, dtype=np.int8)
    ki = k - 3
    C22k = C22K[ki]
    base = PLACEOFF_C[ki]
    for wd in range(M_CANON):
        wr = WR_OF_DENSE[wd]
        W = WOLF_MASKS[wr]
        for sr in range(C22k):
            S = _unrank_sheep(wr, sr, k, FREECELLS, CTAB_FLAT)
            if not _slot_canonical(wr, S, CTAB_FLAT, FREELIST, MIRROR_CELL,
                                   MIRROR_WR):
                continue
            idx = (base + wd * C22k + sr) * 2
            n = _wolf_succs(W, S, Wout, Sout, capout, NEIGH)
            if n == 0:
                exp = SHEEP_WIN
            else:
                has_win = False
                all_lose = True
                for i in range(n):
                    if capout[i]:
                        if k == 3:
                            sv = WOLF_WIN
                        else:
                            sv = tab[_encode_c(Wout[i], Sout[i], SHEEP, PLACEOFF_C,
                                               C22K, CTAB_FLAT, FREELIST, WDEN,
                                               MIRROR_WR, MIRROR_CELL)] & 3
                    else:
                        sv = tab[_encode_c(Wout[i], Sout[i], SHEEP, PLACEOFF_C,
                                           C22K, CTAB_FLAT, FREELIST, WDEN,
                                           MIRROR_WR, MIRROR_CELL)] & 3
                    if sv == WOLF_WIN:
                        has_win = True
                    if sv != SHEEP_WIN:
                        all_lose = False
                exp = WOLF_WIN if has_win else (SHEEP_WIN if all_lose else DRAW)
            if (tab[idx] & 3) != exp:
                bad += 1
            n2 = _sheep_succs(W, S, Sout, NEIGH)
            if n2 == 0:
                exp2 = WOLF_WIN
            else:
                has_win = False
                all_lose = True
                for i in range(n2):
                    sv = tab[_encode_c(W, Sout[i], WOLF, PLACEOFF_C, C22K,
                                       CTAB_FLAT, FREELIST, WDEN,
                                       MIRROR_WR, MIRROR_CELL)] & 3
                    if sv == SHEEP_WIN:
                        has_win = True
                    if sv != WOLF_WIN:
                        all_lose = False
                exp2 = SHEEP_WIN if has_win else (WOLF_WIN if all_lose else DRAW)
            if (tab[idx + 1] & 3) != exp2:
                bad += 1
    return bad


def _worker(args):
    k, tab_dir = args
    t0 = time.time()
    tab = np.load(os.path.join(tab_dir, "full_packed.npy"), mmap_mode="r")
    bad = _verify_one_layer(k, tab, PLACEOFF_C, C22K, WOLF_MASKS, WR_OF_DENSE,
                            FREECELLS, FREELIST, CTAB_FLAT, WDEN, MIRROR_WR,
                            MIRROR_CELL, NEIGH)
    return k, bad, time.time() - t0


def main():
    tab_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "tt_par_full")
    workers = int(sys.argv[2].split("=")[1]) if len(sys.argv) > 2 else 13
    print(f"分层并行复核: 表目录={tab_dir} 进程数={workers}", flush=True)
    t0 = time.time()
    with Pool(workers) as pool:
        results = pool.map(_worker, [(k, tab_dir) for k in range(3, 16)])
    total_bad = 0
    for k, bad, dt in sorted(results):
        total_bad += bad
        print(f"  羊数 {k:2d} 层: 错误 {bad:,}  用时 {dt/60:.1f}min", flush=True)
    print(f"复核完成: 总错误={total_bad:,}  总用时={(time.time()-t0)/60:.1f}min",
          flush=True)


if __name__ == "__main__":
    main()

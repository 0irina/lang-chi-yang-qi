# -*- coding: utf-8 -*-
"""验证 24 个 k=4 狼回合"参考d=0 vs 规范d=1"状态:
参考求解器在播种期把"吃子直接进入羊无路可走"的 k=4 局面当终局(d=0),
少算了狼的这一步吃子;规范表按统一规则 d = 1 + min(同类后继距离) = 1。
本脚本确认:
  1) 参考表中 k=4 狼回合 狼胜且 d=0 的状态恰好 24 个(与不匹配数一致);
  2) 对每个状态,规范表 d=1 且存在 d=0 的吃子后继,满足 d = 1 + min(后继d)。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from rules import WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW
from index import (WOLF_MASKS, FREECELLS, FREELIST, CTAB_FLAT, C22K, SHEEP_OFF,
                   WR_OF_DENSE, MIRROR_WR, MIRROR_CELL, WDEN, PLACEOFF_C)
import endgame_full as EF
from endgame_full import (_encode_c, _unrank_sheep, _decode_c, _wolf_succs, NEIGH)

TT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tt")
NW = 2300


def main():
    value5 = np.load(os.path.join(TT, "tt_3_5.npy"), mmap_mode="r")
    dist5 = np.load(os.path.join(TT, "dist_3_5.npy"), mmap_mode="r")
    tab = np.load(os.path.join(TT, "full_packed.npy"), mmap_mode="r")
    N = EF.full_size(15)
    dist = np.memmap(os.path.join(TT, "full_dist.dat"), dtype=np.uint16,
                     mode="r", shape=(N,))
    ki = 1  # k=4
    Ck = int(C22K[ki])
    base5 = int(SHEEP_OFF[ki]) * NW * 2
    cases = []
    for wr in range(NW):
        W = WOLF_MASKS[wr]
        for sr in range(Ck):
            i5 = base5 + (wr * Ck + sr) * 2
            if value5[i5] == WOLF_WIN and dist5[i5] == 0:
                cases.append((wr, sr))
    print(f"参考表中 k=4 狼回合 狼胜且d=0 的状态总数 = {len(cases)}")
    bad = 0
    Wout = np.empty(64, dtype=np.int64)
    Sout = np.empty(64, dtype=np.int64)
    capout = np.empty(64, dtype=np.int8)
    for wr, sr in cases:
        W = WOLF_MASKS[wr]
        S = _unrank_sheep(wr, sr, 4, FREECELLS, CTAB_FLAT)
        cidx = _encode_c(W, S, WOLF, PLACEOFF_C, C22K, CTAB_FLAT, FREELIST,
                         WDEN, MIRROR_WR, MIRROR_CELL)
        cv = int(tab[cidx] & 3)
        cd = int(dist[cidx])
        if cv != WOLF_WIN or cd != 1:
            print(f"  异常 wr={wr} sr={sr}: canon_v={cv} canon_d={cd}")
            bad += 1
            continue
        ns = _wolf_succs(W, S, Wout, Sout, capout, NEIGH)
        best = -1
        got0 = False
        for i in range(ns):
            if capout[i] and 4 == 3:  # 不可能分支,仅类型完整
                sd = 0
            else:
                e = _encode_c(Wout[i], Sout[i], SHEEP, PLACEOFF_C, C22K,
                              CTAB_FLAT, FREELIST, WDEN, MIRROR_WR, MIRROR_CELL)
                sv = int(tab[e] & 3)
                if sv != WOLF_WIN:
                    continue
                sd = int(dist[e])
            if best < 0 or sd < best:
                best = sd
            if sd == 0:
                got0 = True
        if best < 0 or cd != best + 1 or not got0:
            print(f"  自洽失败 wr={wr} sr={sr}: min_succ_d={best} canon_d={cd}")
            bad += 1
    print(f"全部 {len(cases)} 个状态: {'通过(规范表自洽, d=1+min=1)' if bad == 0 else f'{bad} 个异常'}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

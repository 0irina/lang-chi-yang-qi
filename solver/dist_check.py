# -*- coding: utf-8 -*-
"""精确距离验证(dist_pass 完成后运行)。

Phase A (--phase A, 默认): 穷举 k=3..5 全部局面,与顺序全空间求解器的
  tt_3_5.npy / dist_3_5.npy 逐一比对(镜像不变性保证可比对)。
  这是对精确距离的独立交叉验证,任何种子/波次错误都会暴露。

Phase B (--phase B): 分层抽样 + 均匀抽样共 ~40 万局面,用"局部一致性"验证:
  非终局胜负局面的 dist == 1 + (赢方走子取 min / 输方走子取 max) 同类后继 dist,
  终局局面 dist == 0。

用法(全部小写参数):
  python dist_check.py --phase a      # k<=5 穷举交叉验证(内存小,先跑)
  python dist_check.py --phase b      # 全局抽样局部一致性
  python dist_check.py                # 两个阶段都跑
未出现 tt\\dist_pass_done.flag 时拒绝运行(除非 --force)。
"""
import os
import sys
import time

import numpy as np
from numba import njit

from rules import WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW
from index import (WOLF_MASKS, FREECELLS, FREELIST, CTAB_FLAT, C22K, SHEEP_OFF,
                   M_CANON, WR_OF_DENSE, MIRROR_WR, MIRROR_CELL, WDEN,
                   PLACEOFF_C)
from endgame_full import (_encode_c, _decode_c, _unrank_sheep, _wolf_succs,
                          _sheep_succs, _has_wolf_move, _has_sheep_move,
                          _has_wolf_capture, full_size, default_outdir, NEIGH)

NW = 2300  # C(25,3)


# ---------------- Phase A: k<=5 exhaustive cross-check ----------------
@njit(cache=True)
def _check_k35(value5, dist5, dist_mm, PLACEOFF_C, C22K, WOLF_MASKS, FREECELLS,
               CTAB_FLAT, FREELIST, WDEN, MIRROR_WR, MIRROR_CELL, SHEEP_OFF,
               kstart, kend):
    mism = 0
    checked = 0
    draws = 0
    sat255 = 0
    offbyone = 0
    nwin = np.zeros(16, dtype=np.int64)
    det = np.empty((20, 6), dtype=np.int64)
    ndet = 0
    for ki in range(kstart, kend):
        k = ki + 3
        Ck = C22K[ki]
        base5 = SHEEP_OFF[ki] * NW * 2
        for wr in range(NW):
            W = WOLF_MASKS[wr]
            for sr in range(Ck):
                S = _unrank_sheep(wr, sr, k, FREECELLS, CTAB_FLAT)
                i5 = base5 + (wr * Ck + sr) * 2
                for turn in range(2):
                    v5 = value5[i5 + turn]
                    if v5 == DRAW:
                        draws += 1
                        continue
                    rd = dist5[i5 + turn]
                    cidx = _encode_c(W, S, turn, PLACEOFF_C, C22K, CTAB_FLAT,
                                     FREELIST, WDEN, MIRROR_WR, MIRROR_CELL)
                    d = dist_mm[cidx]
                    checked += 1
                    nwin[k] += 1
                    if d != rd:
                        # 已知参考差异:参考求解器在播种期把 k=4 狼回合"吃子
                        # 直接进入羊无路可走"的局面当终局(d=0),少算狼这一步;
                        # 规范表按统一规则 d=1+min=1。见 verify_24.py。
                        if k == 4 and turn == 0 and v5 == WOLF_WIN \
                                and rd == 0 and d == 1:
                            offbyone += 1
                            continue
                        mism += 1
                        if rd == 255:
                            sat255 += 1
                        if ndet < 20:
                            det[ndet, 0] = k
                            det[ndet, 1] = wr
                            det[ndet, 2] = sr
                            det[ndet, 3] = turn
                            det[ndet, 4] = d
                            det[ndet, 5] = rd
                            ndet += 1
    return mism, checked, draws, sat255, offbyone, nwin, det, ndet


def phase_a(outdir):
    tt = os.path.join(outdir, "tt_3_5.npy")
    dt = os.path.join(outdir, "dist_3_5.npy")
    dp = os.path.join(outdir, "full_dist.dat")
    if not all(os.path.exists(p) for p in (tt, dt, dp)):
        print("MISSING reference files for phase A:", tt, dt, dp)
        return 1
    value5 = np.load(tt)
    dist5 = np.load(dt)
    N = full_size(15)
    dist_mm = np.memmap(dp, dtype=np.uint16, mode="r", shape=(N,))
    t0 = time.time()
    mism, checked, draws, sat255, offbyone, nwin, det, ndet = _check_k35(
        value5, dist5, dist_mm, PLACEOFF_C, C22K, WOLF_MASKS, FREECELLS,
        CTAB_FLAT, FREELIST, WDEN, MIRROR_WR, MIRROR_CELL, SHEEP_OFF, 0, 3)
    print(f"[A] checked={checked:,} draws(skipped)={draws:,} mismatches={mism:,} "
          f"(ref-saturated-255={sat255:,}) (known-ref-offbyone={offbyone:,}) "
          f"time={time.time()-t0:.1f}s")
    for k in range(3, 6):
        print(f"[A]   k={k}: win/loss states checked={nwin[k]:,}")
    if ndet:
        print("[A] first mismatches (k, wr, sr, turn, canonical_d, ref_d):")
        for i in range(ndet):
            print("    ", tuple(int(x) for x in det[i]))
    return 0 if mism == 0 else 1


# ---------------- Phase B: stratified local-consistency sample ----------------
@njit(cache=True)
def _check_sample(tab, dist, idxs, PLACEOFF_C, C22K, WOLF_MASKS, WR_OF_DENSE,
                  FREECELLS, CTAB_FLAT, FREELIST, WDEN, MIRROR_WR, MIRROR_CELL,
                  NEIGH, kmax):
    n = idxs.shape[0]
    Wout = np.empty(64, dtype=np.int64)
    Sout = np.empty(64, dtype=np.int64)
    capout = np.empty(64, dtype=np.int8)
    mism = 0
    checked = 0
    draws = 0
    no_succ = 0
    det = np.empty((20, 7), dtype=np.int64)
    ndet = 0
    hist = np.zeros(64, dtype=np.int64)
    for t in range(n):
        X = idxs[t]
        v = tab[X] & 3
        if v == DRAW or v == 0:
            draws += 1
            continue
        d = dist[X]
        W, S, turn, k = _decode_c(X, PLACEOFF_C, C22K, WOLF_MASKS, WR_OF_DENSE,
                                  FREECELLS, CTAB_FLAT)
        if turn == WOLF:
            if not _has_wolf_move(W, S, NEIGH):
                if d != 0:
                    mism += 1
                    if ndet < 20:
                        det[ndet, 0] = k
                        det[ndet, 1] = turn
                        det[ndet, 2] = X
                        det[ndet, 3] = d
                        det[ndet, 4] = 0
                        det[ndet, 5] = v
                        det[ndet, 6] = -1
                        ndet += 1
                checked += 1
                continue
            if k == 3 and _has_wolf_capture(W, S, NEIGH):
                if d != 0:
                    mism += 1
                    if ndet < 20:
                        det[ndet, 0] = k
                        det[ndet, 1] = turn
                        det[ndet, 2] = X
                        det[ndet, 3] = d
                        det[ndet, 4] = 0
                        det[ndet, 5] = v
                        det[ndet, 6] = -2
                        ndet += 1
                checked += 1
                continue
            ns = _wolf_succs(W, S, Wout, Sout, capout, NEIGH)
            best = -1
            for i in range(ns):
                if capout[i] and k == 3:
                    sv = WOLF_WIN
                    sd = 0
                else:
                    e = _encode_c(Wout[i], Sout[i], SHEEP, PLACEOFF_C, C22K,
                                  CTAB_FLAT, FREELIST, WDEN, MIRROR_WR, MIRROR_CELL)
                    sv = tab[e] & 3
                    sd = dist[e]
                if sv != v:
                    continue
                if best < 0:
                    best = sd
                elif v == WOLF_WIN:
                    if sd < best:
                        best = sd
                else:
                    if sd > best:
                        best = sd
        else:
            if not _has_sheep_move(W, S, NEIGH):
                if d != 0:
                    mism += 1
                    if ndet < 20:
                        det[ndet, 0] = k
                        det[ndet, 1] = turn
                        det[ndet, 2] = X
                        det[ndet, 3] = d
                        det[ndet, 4] = 0
                        det[ndet, 5] = v
                        det[ndet, 6] = -3
                        ndet += 1
                checked += 1
                continue
            ns = _sheep_succs(W, S, Sout, NEIGH)
            best = -1
            for i in range(ns):
                e = _encode_c(W, Sout[i], WOLF, PLACEOFF_C, C22K, CTAB_FLAT,
                              FREELIST, WDEN, MIRROR_WR, MIRROR_CELL)
                sv = tab[e] & 3
                if sv != v:
                    continue
                sd = dist[e]
                if best < 0:
                    best = sd
                elif v == SHEEP_WIN:
                    if sd < best:
                        best = sd
                else:
                    if sd > best:
                        best = sd
        if best < 0:
            no_succ += 1
            continue
        expected = best + 1
        if expected > 65535:
            expected = 65535
        checked += 1
        if d < 64:
            hist[d] += 1
        if d != expected:
            mism += 1
            if ndet < 20:
                det[ndet, 0] = k
                det[ndet, 1] = turn
                det[ndet, 2] = X
                det[ndet, 3] = d
                det[ndet, 4] = expected
                det[ndet, 5] = v
                det[ndet, 6] = best
                ndet += 1
    return mism, checked, draws, no_succ, det, ndet, hist


def build_sample(N, per_layer=25000, extra=75000, seed=12345):
    rng = np.random.default_rng(seed)
    parts = []
    for ki in range(13):
        lo = int(PLACEOFF_C[ki]) * 2
        hi = lo + int(M_CANON) * int(C22K[ki]) * 2
        parts.append(rng.integers(lo, hi, size=per_layer, dtype=np.uint64))
    parts.append(rng.integers(0, N, size=extra, dtype=np.uint64))
    idxs = np.concatenate(parts)
    idxs.sort()
    return idxs


def phase_b(outdir):
    tab_path = os.path.join(outdir, "full_packed.npy")
    dp = os.path.join(outdir, "full_dist.dat")
    N = full_size(15)
    print("[B] loading packed value table (9.6GB)...")
    tab = np.load(tab_path)
    dist = np.memmap(dp, dtype=np.uint16, mode="r", shape=(N,))
    idxs = build_sample(N)
    print(f"[B] sample size={idxs.shape[0]:,}")
    t0 = time.time()
    mism, checked, draws, no_succ, det, ndet, hist = _check_sample(
        tab, dist, idxs, PLACEOFF_C, C22K, WOLF_MASKS, WR_OF_DENSE, FREECELLS,
        CTAB_FLAT, FREELIST, WDEN, MIRROR_WR, MIRROR_CELL, NEIGH, 15)
    print(f"[B] checked={checked:,} draws(skipped)={draws:,} "
          f"no_same_class_succ={no_succ:,} mismatches={mism:,} "
          f"time={time.time()-t0:.1f}s")
    if hist.sum():
        print("[B] dist histogram (0..63):",
              " ".join(str(int(x)) for x in hist[:32]))
    if ndet:
        print("[B] first mismatches (k, turn, X, stored_d, expected, v, best_succ_d):")
        for i in range(ndet):
            print("    ", tuple(int(x) for x in det[i]))
    return 0 if (mism == 0 and no_succ == 0) else 1


def main():
    outdir = default_outdir()
    flag = os.path.join(outdir, "dist_pass_done.flag")
    args = sys.argv[1:]
    force = "--force" in args
    if not os.path.exists(flag) and not force:
        print("REFUSED: dist_pass_done.flag not found at", flag,
              "(pass still running or failed; use --force to override)")
        return 2
    do_a = (not args) or "--phase" in args and "a" in args[args.index("--phase") + 1]
    do_b = (not args) or "--phase" in args and "b" in args[args.index("--phase") + 1]
    rc = 0
    if do_a:
        rc |= phase_a(outdir)
    if do_b:
        rc |= phase_b(outdir)
    print("RESULT:", "ALL OK" if rc == 0 else "MISMATCHES FOUND")
    return rc


if __name__ == "__main__":
    sys.exit(main())

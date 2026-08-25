# -*- coding: utf-8 -*-
"""中局压力研究:和棋中局(羊走)里,羊能否把"狼正招数"压到极少?
- 采样:随机走"和棋着法"的中局局面(羊数 8..13,羊走);
- 指标:每个局面下,羊各和棋着法对应的后继"狼正招数"(狼走后仍和棋的
  着法数);比较 全部和棋着法的最小正招数 与 引擎当前首选的正招数。
结论用于决定是否给羊方新增"狼正招数少"键。
"""
import os
import sys
import random
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import endgame
from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW,
                   pos_name, wolf_moves, sheep_moves,
                   apply_wolf_move, apply_sheep_move, popcount,
                   INIT_WOLVES, INIT_SHEEP)
from engine import Engine

N_SAMPLES = 200
K_MIN, K_MAX = 8, 13

_lc = {}


def L(w, s, turn):
    key = (w, s, turn)
    v = _lc.get(key)
    if v is None:
        v = endgame.lookup(w, s, turn)
        if len(_lc) > 4_000_000:
            _lc.clear()
        _lc[key] = v
    return v


def wolf_counts(w, s):
    """狼走局面:返回 (正招数=走后仍和棋, 败着数, 总着数)。"""
    wc = wb = wt = 0
    for a, b, cap in wolf_moves(w, s):
        w2, s2 = apply_wolf_move(w, s, a, b)
        wt += 1
        if popcount(s2) <= 3:
            continue
        v = L(w2, s2, SHEEP)
        if v == DRAW:
            wc += 1
        elif v == SHEEP_WIN:
            wb += 1
    return wc, wb, wt


def draw_sheep_moves(w, s):
    out = []
    for a, b in sheep_moves(w, s):
        w2, s2 = apply_sheep_move(w, s, a, b)
        if L(w2, s2, WOLF) == DRAW:
            out.append((a, b))
    return out


def sample_midgame(rng):
    """随机走和棋着法,采一个羊走的中局局面(羊数 8..13)。"""
    w, s = INIT_WOLVES, INIT_SHEEP
    turn = WOLF
    for _ in range(200):
        k = popcount(s)
        if K_MIN <= k <= K_MAX and turn == SHEEP:
            return w, s
        if turn == WOLF:
            cand = []
            for a, b, cap in wolf_moves(w, s):
                w2, s2 = apply_wolf_move(w, s, a, b)
                if popcount(s2) <= 3 or L(w2, s2, SHEEP) == DRAW:
                    cand.append((a, b, cap))
            if not cand:
                return None
            a, b, cap = rng.choice(cand)
            w, s = apply_wolf_move(w, s, a, b)
            turn = SHEEP
        else:
            cand = draw_sheep_moves(w, s)
            if not cand:
                return None
            a, b = rng.choice(cand)
            w, s = apply_sheep_move(w, s, a, b)
            turn = WOLF
    return None


def main():
    t0 = time.time()
    endgame.load_tables()
    eng = Engine()
    eng.opening_variety = False
    rng = random.Random(20260825)

    hist_min = []
    hist_eng = []
    gap = 0
    n_eq = 0
    n_corr1 = 0
    n_give_cap = 0          # 最小正招着法里存在"送安全吃"的样本
    n_mincap_gives = 0      # 达成最小正招的着法里,是否包含送安全吃的选项
    samples = 0
    while samples < N_SAMPLES:
        st = sample_midgame(rng)
        if st is None:
            continue
        w, s = st
        sdm = draw_sheep_moves(w, s)
        if not sdm:
            continue
        samples += 1
        best = (99, None, None)
        for a, b in sdm:
            w2, s2 = apply_sheep_move(w, s, a, b)
            wc, wb, wt = wolf_counts(w2, s2)
            # 安全吃子数(送子检测)
            scaps = 0
            for fa, fb, cap in wolf_moves(w2, s2):
                if not cap:
                    continue
                w3, s3 = apply_wolf_move(w2, s2, fa, fb)
                if popcount(s3) <= 3 or L(w3, s3, SHEEP) != SHEEP_WIN:
                    scaps += 1
            if wc < best[0]:
                best = (wc, (a, b), scaps)
            elif wc == best[0] and scaps < best[2]:
                best = (wc, (a, b), scaps)
        min_wc, bmv, bcap = best
        hist_min.append(min_wc)
        if min_wc == 1:
            n_corr1 += 1
        if bcap > 0:
            n_mincap_gives += 1
        # 引擎首选
        try:
            mv, info = eng.best_move(w, s, SHEEP, history=())
        except Exception:
            mv = None
        if mv is None:
            continue
        w2, s2 = apply_sheep_move(w, s, mv[0], mv[1])
        wc_eng, wb_eng, wt_eng = wolf_counts(w2, s2)
        hist_eng.append(wc_eng)
        if wc_eng == min_wc:
            n_eq += 1
        gap += wc_eng - min_wc
        if samples % 20 == 0:
            print(f"  采样 {samples}/{N_SAMPLES}  "
                  f"耗时 {time.time()-t0:.0f}s", flush=True)

    def dist(hist):
        out = {}
        for x in hist:
            out[x] = out.get(x, 0) + 1
        return out

    print("=" * 60)
    print(f"样本数: {samples}  耗时 {time.time()-t0:.0f}s")
    print("羊各和棋着法可达的【最小狼正招数】分布:",
          dict(sorted(dist(hist_min).items())))
    print(f"  其中 最小正招=1(狼唯一正招) 的样本: {n_corr1} "
          f"({n_corr1/max(1,samples)*100:.0f}%)")
    print("引擎当前首选对应的【狼正招数】分布:",
          dict(sorted(dist(hist_eng).items())))
    print(f"引擎首选已达成最小正招: {n_eq}/{len(hist_eng)} "
          f"({n_eq/max(1,len(hist_eng))*100:.0f}%)")
    print(f"引擎首选平均多给狼正招: {gap/max(1,len(hist_eng)):.2f} 条")
    print(f"达成最小正招的着法中含'送安全吃'的样本: {n_mincap_gives}")
    print("=" * 60)


if __name__ == "__main__":
    main()

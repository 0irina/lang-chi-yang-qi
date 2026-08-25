# -*- coding: utf-8 -*-
"""中局精度压力测试:随机中局和棋局面(羊走,羊数8..13)下,
引擎羊方首选必须达成"不送子同档内的最小狼正招数"(精度压力键)。
依据 mid_corr_study.py:93% 的中局局面羊可把狼压到唯一正招。"""
import os
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import endgame
from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW,
                   wolf_moves, sheep_moves,
                   apply_wolf_move, apply_sheep_move, popcount,
                   INIT_WOLVES, INIT_SHEEP)
import opening_book
import opening_book2
from engine import Engine

N_SAMPLES = 80
K_MIN, K_MAX = 8, 13


def L(w, s, turn):
    return endgame.lookup(w, s, turn)


def draw_sheep_moves(w, s):
    out = []
    for a, b in sheep_moves(w, s):
        w2, s2 = apply_sheep_move(w, s, a, b)
        if L(w2, s2, WOLF) == DRAW:
            out.append((a, b))
    return out


def sample_midgame(rng):
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


def key4(eng, w, s, frm, to):
    """(rep, bk, safe, wcorr) 前缀键,与引擎羊方和棋排序一致。
    bk: 0=主选书 1=次选书 2=常规。"""
    w2, s2 = apply_sheep_move(w, s, frm, to)
    rep = eng._wolf_can_repeat(w2, s2, set())
    bm = opening_book.BOOK.get((w, s))
    bm2 = opening_book2.BOOK2.get((w, s))
    if bm and (frm, to) in bm:
        bk = 0
    elif bm2 and (frm, to) in bm2:
        bk = 1
    else:
        bk = 2
    safe = eng._wolf_safe_caps(w2, s2)
    bad, tot = eng._opp_err(w2, s2, WOLF)
    return (rep, bk, safe, tot - bad)


def main():
    endgame.load_tables()
    eng = Engine()
    eng.opening_variety = False
    rng = random.Random(20260825)
    n = 0
    n_corr1 = 0
    while n < N_SAMPLES:
        st = sample_midgame(rng)
        if st is None:
            continue
        w, s = st
        sdm = draw_sheep_moves(w, s)
        if not sdm:
            continue
        mv, info = eng.best_move(w, s, SHEEP, history=())
        assert info["value"] == DRAW
        got = key4(eng, w, s, mv[0], mv[1])
        best = min(key4(eng, w, s, a, b) for a, b in sdm)
        assert got == best, \
            f"键不一致: got={got} best={best} @ 羊{mv}"
        if got[3] == 1:
            n_corr1 += 1
        n += 1
    print(f"中局精度压力: {n} 样本全部键一致 OK;"
          f" 引擎首选把狼压到唯一正招 {n_corr1}/{n} "
          f"({n_corr1 / n * 100:.0f}%)")
    print("RESULT: ALL OK")


if __name__ == "__main__":
    main()

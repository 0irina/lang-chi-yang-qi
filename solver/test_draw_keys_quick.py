# -*- coding: utf-8 -*-
"""快速键一致性抽查(30样本):羊键/狼键镜像与引擎一致,供快速回归。"""
import os
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules import WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, wolf_moves, \
    sheep_moves, apply_wolf_move, apply_sheep_move, pos_name
import endgame
import winrate
import opening_book
import opening_book2
from engine import Engine

eng = Engine()
rng = random.Random(123)


def wolf_key(w, s, m, hist_set=None):
    ww, ss = apply_wolf_move(w, s, m[0], m[1])
    b, t = eng._opp_err(ww, ss, SHEEP)
    ratio = b / t if t else 0.0
    scorr = t - b
    eat = eng._wolf_eat_potential(ww, ss)
    wsc = winrate.score_position(ww, ss, SHEEP, eng=eng,
                                 depth=eng.score_depth)[0]
    if hist_set:
        inh = (ww, ss) in hist_set
        zug = eng._sheep_zugzwang(ww, ss, hist_set)
        return (scorr, -eat, -wsc, -inh, -zug, 0 if m[2] else 1, -ratio)
    return (scorr, -eat, -wsc, 0, 0, 0 if m[2] else 1, -ratio)


bad_w = bad_s = 0
n_w = n_s = 0
trials = 0
while (n_w < 30 or n_s < 30) and trials < 100000:
    trials += 1
    cells = rng.sample(range(25), 3 + rng.choice([4, 5, 6, 7, 8]))
    w = sum(1 << c for c in cells[:3])
    s = sum(1 << c for c in cells[3:])
    if endgame.lookup(w, s, WOLF) == DRAW and n_w < 30:
        n_w += 1
        mv, info = eng.best_move(w, s, WOLF, history=())
        if info["value"] == DRAW:
            best = None
            for m in wolf_moves(w, s):
                ww, ss = apply_wolf_move(w, s, m[0], m[1])
                if endgame.lookup(ww, ss, SHEEP) != DRAW:
                    continue
                kk = wolf_key(w, s, m)
                if best is None or kk < best:
                    best = kk
            if wolf_key(w, s, mv) != best:
                bad_w += 1
                print(f"  [狼键不符] got={wolf_key(w, s, mv)} best={best}")
    if endgame.lookup(w, s, SHEEP) == DRAW and n_s < 30:
        n_s += 1
        mv, info = eng.best_move(w, s, SHEEP, history=())
        if info["value"] != DRAW:
            bad_s += 1
            continue
        w2, s2 = apply_sheep_move(w, s, mv[0], mv[1])
        got_safe = eng._wolf_safe_caps(w2, s2)
        got_poison = eng._wolf_losing_caps(w2, s2)
        got_thr = eng._wolf_cap_threat(w2, s2)
        got_sal = eng._salient_err(w2, s2)
        got_bad, got_tot = eng._opp_err(w2, s2, WOLF)
        got_wcorr = got_tot - got_bad
        gbm = opening_book.BOOK.get((w, s))
        gbm2 = opening_book2.BOOK2.get((w, s))
        if gbm and (mv[0], mv[1]) in gbm:
            got_bk = 0
        elif gbm2 and (mv[0], mv[1]) in gbm2:
            got_bk = 1
        else:
            got_bk = 2
        got_drop = eng._bait_score_drop(w2, s2) if got_safe > 0 else 0.0
        got_score = winrate.score_position(w2, s2, WOLF, eng=eng,
                                           depth=eng.score_depth)[0]
        got_chn = eng._pressure_chain(w2, s2)
        got_sca = got_score - 25 * min(got_chn, 8)
        best = None
        for frm, to in sheep_moves(w, s):
            ww, ss = apply_sheep_move(w, s, frm, to)
            if endgame.lookup(ww, ss, WOLF) != DRAW:
                continue
            bmn = opening_book.BOOK.get((w, s))
            bmn2 = opening_book2.BOOK2.get((w, s))
            if bmn and (frm, to) in bmn:
                bkn = 0
            elif bmn2 and (frm, to) in bmn2:
                bkn = 1
            else:
                bkn = 2
            sc = eng._wolf_safe_caps(ww, ss)
            ps = eng._wolf_losing_caps(ww, ss)
            dp = eng._bait_score_drop(ww, ss) if sc > 0 else 0.0
            thr = eng._wolf_cap_threat(ww, ss)
            sal = eng._salient_err(ww, ss)
            badn, totn = eng._opp_err(ww, ss, WOLF)
            wc = totn - badn
            scm = winrate.score_position(ww, ss, WOLF, eng=eng,
                                         depth=eng.score_depth)[0]
            chn = eng._pressure_chain(ww, ss)
            sca = scm - 25 * min(chn, 8)
            key = (bkn, sc, wc, thr, sca, 0, -dp, -badn, -sal, -ps)
            if best is None or key < best:
                best = key
        best_bk, best_sc, best_wc, best_thr, best_scm, best_rc, \
            neg_dp, neg_bad, neg_sal, neg_ps = best
        if (got_bk != best_bk or got_safe != best_sc
                or got_wcorr != best_wc or got_thr != best_thr
                or got_sca > best_scm + 1e-6
                or got_drop + 1e-9 < -neg_dp
                or got_bad != -neg_bad
                or got_sal + 1e-9 < -neg_sal
                or -got_poison != neg_ps):
            bad_s += 1
            print(f"  [羊键不符] bk={got_bk}({best_bk}) "
                  f"safe={got_safe}({best_sc}) wcorr={got_wcorr}({best_wc}) "
                  f"thr={got_thr}({best_thr}) sca={got_sca:.0f}({best_scm:.0f})")

print(f"快速键抽查: 狼 {n_w} 例失败 {bad_w}; 羊 {n_s} 例失败 {bad_s}")
print("RESULT:", "ALL OK" if (bad_w == 0 and bad_s == 0) else "FAIL")

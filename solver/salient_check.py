# -*- coding: utf-8 -*-
"""验证:"显眼败招数"(狼方高显眼度走法中直接羊胜的数量)是否与
强手模型 P(羊胜) 正相关 —— 若相关,则作为羊方和棋选招的排序键。
显眼度:吃子3 / 走向中心2 / 一般1 / 退避0.4(与 strong_model 一致)。
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, popcount,
                   wolf_moves, sheep_moves, apply_wolf_move, apply_sheep_move)
import endgame
from engine import Engine
from strong_model import _eval_wolf_turn

endgame.load_tables()
eng = Engine()
CENTER_DIST = {(r, c): max(abs(r - 2), abs(c - 2)) for r in range(5)
               for c in range(5)}


def salience(frm, to, cap):
    if cap:
        return 3.0
    d1 = CENTER_DIST[(frm // 5, frm % 5)]
    d2 = CENTER_DIST[(to // 5, to % 5)]
    if d2 < d1:
        return 2.0
    if d2 > d1:
        return 0.4
    return 1.0


def salient_losses(w, s):
    """狼走局面:高显眼度走法中,走后直接羊胜(且非吃胜)的数量加权和"""
    tot = 0.0
    for frm, to, cap in wolf_moves(w, s):
        w2, s2 = apply_wolf_move(w, s, frm, to)
        if popcount(s2) <= 3:
            continue
        if endgame.lookup(w2, s2, SHEEP) == SHEEP_WIN:
            tot += salience(frm, to, cap)
    return tot


rng = random.Random(20260824)
pairs = []
trials = 0
while len(pairs) < 150 and trials < 400000:
    trials += 1
    k = rng.choice([5, 6, 7, 8, 9, 10])
    cells = rng.sample(range(25), 3 + k)
    w = sum(1 << c for c in cells[:3])
    s = sum(1 << c for c in cells[3:])
    if endgame.lookup(w, s, SHEEP) != DRAW:
        continue
    for frm, to in sheep_moves(w, s):
        w2, s2 = apply_sheep_move(w, s, frm, to)
        if endgame.lookup(w2, s2, WOLF) != DRAW:
            continue
        sl = salient_losses(w2, s2)
        p = _eval_wolf_turn(w2, s2, 2)   # 深度2,快速
        pairs.append((sl, p))
        break

# 按 sl 分桶看 P(羊胜) 均值
buckets = {}
for sl, p in pairs:
    b = 0 if sl < 0.5 else (1 if sl < 1.5 else (2 if sl < 3 else 3))
    buckets.setdefault(b, []).append(p)
print("显眼败招数 vs 强手模型P(羊胜)(150样本,深度2):")
for b in sorted(buckets):
    ps = buckets[b]
    print(f"  sl桶={b}  n={len(ps):>3}  P均值={sum(ps)/len(ps):.4f}  "
          f"最大={max(ps):.4f}")
# 相关性
import statistics
sls = [x[0] for x in pairs]
ps = [x[1] for x in pairs]
ms, mp = statistics.mean(sls), statistics.mean(ps)
cov = sum((a - ms) * (b - mp) for a, b in pairs) / len(pairs)
sd1 = statistics.pstdev(sls)
sd2 = statistics.pstdev(ps)
corr = cov / (sd1 * sd2) if sd1 and sd2 else 0
print(f"相关系数 = {corr:.3f}")

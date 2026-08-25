# -*- coding: utf-8 -*-
"""对比羊方"陷阱"指标的多种形态与强手模型 P(羊胜) 的相关性:
用户观点:唯一应手陷阱没用(唯一正招最明显);真正让高手吃力的是
"路很多 + 其中好几条会输"。
候选指标(狼走局面,羊走后):
  m1 = salient        : 显眼败招加权和(现有)
  m2 = bad * total    : 多路×多败
  m3 = bad            : 败招数
  m4 = bad * (total-bad): 多败×多路(非败)
  m5 = bad + total    : 简单和
  m6 = bad*(bad>=2)   : 至少2条败路
"""
import os
import random
import statistics
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


def metrics(w, s):
    bad = 0
    total = 0
    salient = 0.0
    for frm, to, cap in wolf_moves(w, s):
        w2, s2 = apply_wolf_move(w, s, frm, to)
        if popcount(s2) <= 3:
            continue
        total += 1
        if endgame.lookup(w2, s2, SHEEP) == SHEEP_WIN:
            bad += 1
            if cap:
                salient += 3.0
            else:
                d1 = CENTER_DIST[(frm // 5, frm % 5)]
                d2 = CENTER_DIST[(to // 5, to % 5)]
                salient += 2.0 if d2 < d1 else (0.4 if d2 > d1 else 1.0)
    return dict(bad=bad, total=total, salient=salient,
                m2=bad * total, m3=bad, m4=bad * (total - bad),
                m5=bad + total, m6=bad if bad >= 2 else 0)


rng = random.Random(20260824)
rows = []
trials = 0
while len(rows) < 200 and trials < 400000:
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
        m = metrics(w2, s2)
        p = _eval_wolf_turn(w2, s2, 2)
        m["P"] = p
        rows.append(m)
        break

print(f"样本: {len(rows)} 个羊走后和棋局面\n")
for name in ("salient", "m2", "m3", "m4", "m5", "m6"):
    xs = [r[name] for r in rows]
    ps = [r["P"] for r in rows]
    mx, mp = statistics.mean(xs), statistics.mean(ps)
    cov = sum((a - mx) * (b - mp) for a, b in zip(xs, ps)) / len(rows)
    sd1 = statistics.pstdev(xs)
    sd2 = statistics.pstdev(ps)
    corr = cov / (sd1 * sd2) if sd1 and sd2 else 0
    print(f"  {name:>8}: 相关系数 = {corr:.3f}   (均值 {mx:.2f})")

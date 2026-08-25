# -*- coding: utf-8 -*-
"""骗招/软诱饵统计(新表):
  真毒 = 狼吃后直接羊胜(_wolf_losing_caps>0);
  软诱饵 = 狼可安全吃(safe>=1),但吃完后的局面狼"败招数"多(走得难受)。
统计:羊方和棋后继中,软诱饵的"吃后危险度"分布,以及与强手模型 P(羊胜) 的
关系——决定是否值得让羊主动送软诱饵。"""
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, popcount,
                   wolf_moves, sheep_moves, apply_wolf_move, apply_sheep_move)
import endgame
from engine import Engine
from strong_model import _eval_wolf_turn

endgame.load_tables()
eng = Engine()
rng = random.Random(20260824)


def post_eat_danger(w, s):
    """狼在(w,s)(狼走)安全吃子后,局面里狼的败招数(最小者=狼挑最安全的吃)"""
    danger = None
    for frm, to, cap in wolf_moves(w, s):
        if not cap:
            continue
        w2, s2 = apply_wolf_move(w, s, frm, to)
        if popcount(s2) <= 3:
            return 0  # 直接吃胜,无危险
        if endgame.lookup(w2, s2, SHEEP) == SHEEP_WIN:
            continue  # 毒吃,狼不会选
        bad, tot = eng._opp_err(w2, s2, SHEEP)
        if danger is None or bad < danger:
            danger = bad
    return danger if danger is not None else 0


rows = []
trials = 0
while len(rows) < 2500 and trials < 500000:
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
        safe = eng._wolf_safe_caps(w2, s2)
        danger = post_eat_danger(w2, s2)
        rows.append((safe, danger))
        break

print(f"样本: {len(rows)} 个羊走后和棋局面\n")
acc = defaultdict(lambda: [0, 0, 0.0])
for safe, danger in rows:
    acc[(safe, danger >= 2)][0] += 1
    acc[(safe, danger >= 2)][1] += danger
print(f"{'安全吃子数':>8} {'吃后危险(败招>=2)?':>12} {'样本':>6} {'吃后败招数均值':>10}")
for (safe, dg), (n, ds, _) in sorted(acc.items()):
    print(f"{safe:>8} {str(dg):>12} {n:>6} {ds/n:>12.2f}")

# 软诱饵 vs 不送子 的强手模型胜率对比(抽样各120)
bait_p = []
safe_p = []
for safe, danger in rows[:1200]:
    pass  # 上面没存局面,重新采
bait_ps = []
safe_ps = []
trials = 0
while (len(bait_ps) < 120 or len(safe_ps) < 120) and trials < 500000:
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
        safe = eng._wolf_safe_caps(w2, s2)
        danger = post_eat_danger(w2, s2)
        p = _eval_wolf_turn(w2, s2, 2)
        if safe >= 1 and danger >= 2 and len(bait_ps) < 120:
            bait_ps.append(p)
        elif safe == 0 and len(safe_ps) < 120:
            safe_ps.append(p)
        break

if bait_ps and safe_ps:
    print(f"\n软诱饵(可吃+吃后败招>=2): n={len(bait_ps)} "
          f"P(羊胜)均值={sum(bait_ps)/len(bait_ps):.4f}")
    print(f"不送子(safe=0)        : n={len(safe_ps)} "
          f"P(羊胜)均值={sum(safe_ps)/len(safe_ps):.4f}")

# -*- coding: utf-8 -*-
"""专家中心阵研究(新表):
狼 C2,C3,C5(格 17,12,2),羊 A4,B4,D4,A2,B2,D2,E2,B1,C1,D1(10只)。
  1. 双方局面值(新规则);
  2. 狼 6 个走法逐个:走后值/距离/显眼度 —— 高手的"错步率"与"冷着"分布;
  3. 强手模型下 P(羊胜);
  4. 对比:中四角占位数 vs 狼吃子威胁/深度2压力(随机局面,新尺子)。
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, WIN_NAMES,
                   pos_name, popcount, wolf_moves, sheep_moves,
                   apply_wolf_move, apply_sheep_move, INIT_WOLVES, INIT_SHEEP)
import endgame
from engine import Engine
from strong_model import _eval_wolf_turn, wolf_distribution

endgame.load_tables()
eng = Engine()

# ---- 专家中心阵 ----
W_C = (1 << 2) | (1 << 12) | (1 << 17)          # C5,C3,C2
S_C = 0
for p in (5, 6, 8, 15, 16, 18, 19, 21, 22, 23):  # A4,B4,D4,A2,B2,D2,E2,B1,C1,D1
    S_C |= 1 << p

print("=== 专家中心阵(狼C2,C3,C5 + 10羊) ===")
for turn, nm in ((WOLF, "狼走"), (SHEEP, "羊走")):
    v = endgame.lookup(W_C, S_C, turn)
    d = endgame.lookup_dist(W_C, S_C, turn)
    print(f"  {nm}: {WIN_NAMES.get(v)}  距离={d}")
print("\n狼的每个走法(狼走局面):")
for frm, to, cap in wolf_moves(W_C, S_C):
    w2, s2 = apply_wolf_move(W_C, S_C, frm, to)
    if popcount(s2) <= 3:
        v = "狼胜"
    else:
        v = WIN_NAMES.get(endgame.lookup(w2, s2, SHEEP))
    d2 = endgame.lookup_dist(w2, s2, SHEEP)
    print(f"  狼 {pos_name(frm)}→{pos_name(to)}{' 吃' if cap else ''}  "
          f"→ {v} (d={d2})")
dist = wolf_distribution(W_C, S_C)
print("\n强手模型下的狼走法概率分布:")
for (frm, to, cap), prob in dist:
    print(f"  狼 {pos_name(frm)}→{pos_name(to)}{' 吃' if cap else ''}  "
          f"prob={prob:.3f}")
p = _eval_wolf_turn(W_C, S_C, 3)
print(f"P(羊胜 | 中心阵, 狼走) = {p:.4f}")

# ---- 随机和棋局面基准(羊走,其后继) ----
print("\n=== 中四角占位 vs 狼吃子威胁/深度2压力(随机羊走和棋后继,新表) ===")
CENTER = {6, 8, 16, 18}
rows = []
trials = 0
while len(rows) < 1200 and trials < 400000:
    trials += 1
    import random
    rng = random.Random(trials)
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
        cent = popcount(s2 & sum(1 << c for c in CENTER))
        safe = eng._wolf_safe_caps(w2, s2)
        threat = eng._wolf_cap_threat(w2, s2)
        rows.append((cent, safe, threat))
        break
    if len(rows) >= 1200:
        break

acc = defaultdict(lambda: [0, 0, 0])
for cent, safe, threat in rows:
    acc[cent][0] += 1
    acc[cent][1] += safe
    acc[cent][2] += threat
print(f"{'中四角占位':>8} {'样本':>6} {'狼安全吃子均值':>10} {'狼2回合吃子威胁均值':>12}")
for c in sorted(acc):
    n, s_, t_ = acc[c]
    print(f"{c:>8} {n:>6} {s_/n:>12.2f} {t_/n:>14.2f}")

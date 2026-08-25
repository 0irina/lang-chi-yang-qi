# -*- coding: utf-8 -*-
"""在第10手局面(狼B4→B5之后,羊走),枚举羊的全部走法,
统计每步走后狼的"安全吃子数"——若全>0,说明此时狼吃第3只已无法避免
(引擎此前的走法并非堡垒最优);若存在=0的招,羊即可在此保羊。"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import endgame
from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, WIN_NAMES,
                   pos_name, popcount, wolf_moves, sheep_moves,
                   apply_wolf_move, apply_sheep_move, INIT_WOLVES,
                   INIT_SHEEP)

endgame.load_tables()

NOTATION = ["狼 2 12", "羊 10 5", "狼 1 6", "羊 11 10", "狼 3 13",
            "羊 10 11", "狼 13 8", "羊 18 13", "狼 6 1", "羊 17 18"]
w, s = INIT_WOLVES, INIT_SHEEP
hist = [(w, s)]
for line in NOTATION:
    p = line.split()
    frm, to = int(p[1]), int(p[2])
    if p[0] == "狼":
        w, s = apply_wolf_move(w, s, frm, to)
    else:
        w, s = apply_sheep_move(w, s, frm, to)
    hist.append((w, s))
    print(f"  {line} → 羊剩 {popcount(s)}")

print("第10手局面(羊走), 羊剩", popcount(s), "只")
print("各走法走后狼的安全吃子数:")
rows = []
for frm, to in sheep_moves(w, s):
    w2, s2 = apply_sheep_move(w, s, frm, to)
    v = endgame.lookup(w2, s2, WOLF)
    safe = 0
    for f2, t2, c2 in wolf_moves(w2, s2):
        if not c2:
            continue
        w3, s3 = apply_wolf_move(w2, s2, f2, t2)
        if popcount(s3) <= 3 or endgame.lookup(w3, s3, SHEEP) != SHEEP_WIN:
            safe += 1
    rows.append((safe, frm, to, v))
rows.sort()
for safe, frm, to, v in rows:
    print(f"  羊 {pos_name(frm)}→{pos_name(to)}  安全吃子={safe}  "
          f"走后值={WIN_NAMES.get(v)}")

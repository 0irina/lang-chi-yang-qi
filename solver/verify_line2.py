# -*- coding: utf-8 -*-
"""核对第二盘棋谱:每手羊是否最优(引擎口径),统计狼吃了几只。"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import endgame
from engine import Engine
from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, pos_name,
                   popcount, wolf_moves, sheep_moves, apply_wolf_move,
                   apply_sheep_move, INIT_WOLVES, INIT_SHEEP)

endgame.load_tables()
eng = Engine()
eng.opening_variety = False

NOTATION = """狼 C5→C3 吃
羊 A3→A4
狼 B5→B4
羊 B3→A3
狼 D5→D3 吃
羊 A3→B3
狼 D3→D4
羊 D2→D3
狼 B4→B5
羊 C2→D2
狼 B5→B3 吃"""

moves = []
for line in NOTATION.strip().splitlines():
    p = line.split()
    a, b = p[1].split("→")
    frm = (5 - int(a[1])) * 5 + (ord(a[0]) - 65)
    to = (5 - int(b[1])) * 5 + (ord(b[0]) - 65)
    moves.append((p[0], frm, to))

w, s = INIT_WOLVES, INIT_SHEEP
hist = [(w, s)]
for i, (who, frm, to) in enumerate(moves, 1):
    if who == "羊":
        best, info = eng.best_move(w, s, SHEEP, history=tuple(hist),
                                   ply_budget=300)
        tag = ""
        if (frm, to) != (best[0], best[1]):
            tag = (f"  ★非最优(引擎走 {pos_name(best[0])}→"
                   f"{pos_name(best[1])})")
        print(f"第{i}手 羊 {pos_name(frm)}→{pos_name(to)}{tag}")
        w, s = apply_sheep_move(w, s, frm, to)
    else:
        w2, s2 = apply_wolf_move(w, s, frm, to)
        cap = popcount(s) > popcount(s2)
        print(f"第{i}手 狼 {pos_name(frm)}→{pos_name(to)}"
              f"{' 吃' if cap else ''}")
        w, s = w2, s2
    hist.append((w, s))
print("剩余羊数:", popcount(s))

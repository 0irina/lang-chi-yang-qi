# -*- coding: utf-8 -*-
"""核对用户棋谱:狼吃了3只,检查每次被吃前羊是否有更优防守避免。
对照引擎最优(带重复回避),找出羊的失误点。"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import endgame
from engine import Engine
from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, WIN_NAMES,
                   pos_name, popcount, wolf_moves, sheep_moves,
                   apply_wolf_move, apply_sheep_move, INIT_WOLVES, INIT_SHEEP)

endgame.load_tables()
eng = Engine()
eng.opening_variety = False

NOTATION = """狼 C5→C3 吃
羊 B3→B4
狼 D5→D3 吃
羊 A3→A4
狼 D3→D4
羊 B4→C4
狼 D4→E4
羊 C4→D4
狼 B5→B4
羊 D4→D3
狼 C3→C4
羊 B2→B3
狼 C4→C2 吃"""


def parse():
    out = []
    for line in NOTATION.strip().splitlines():
        parts = line.split()
        who, mv = parts[0], parts[1]
        a, b = mv.split("→")
        frm = (5 - int(a[1])) * 5 + (ord(a[0]) - 65)
        to = (5 - int(b[1])) * 5 + (ord(b[0]) - 65)
        out.append((who, frm, to))
    return out


w, s = INIT_WOLVES, INIT_SHEEP
hist = [(w, s)]
eaten = 0
for i, (who, frm, to) in enumerate(parse(), 1):
    if who == "羊":
        # 羊走之前:引擎最优是什么?有没有办法避免下一步被吃
        best, info = eng.best_move(w, s, SHEEP, history=tuple(hist),
                                   ply_budget=300)
        best_safe = None
        if best is not None:
            wb, sb = apply_sheep_move(w, s, best[0], best[1])
            caps = [m for m in wolf_moves(wb, sb) if m[2]
                    and (popcount(apply_wolf_move(wb, sb, m[0], m[1])[1]) <= 3
                         or endgame.lookup(
                             *apply_wolf_move(wb, sb, m[0], m[1]),
                             SHEEP) != SHEEP_WIN)]
            best_safe = len(caps)
        mark = "" if (frm, to) == (best[0], best[1]) else \
            f"  ★羊没走最优(引擎走 {pos_name(best[0])}→{pos_name(best[1])},"
        if best_safe is not None and best_safe == 0:
            mark += f" 最优招后狼无安全吃子"
        if mark:
            print(f"第{i}手(羊走前): {mark}")
        w, s = apply_sheep_move(w, s, frm, to)
    else:
        cap = popcount(s) - popcount(apply_wolf_move(w, s, frm, to)[1]) > 0
        w, s = apply_wolf_move(w, s, frm, to)
        if cap:
            eaten += 1
            print(f"第{i}手: 狼吃第{eaten}只 ({pos_name(frm)}→{pos_name(to)})")
    hist.append((w, s))
print(f"\n该线共被吃 {eaten} 只;局面值(狼走)={WIN_NAMES.get(endgame.lookup(w, s, WOLF))}")

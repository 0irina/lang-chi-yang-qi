# -*- coding: utf-8 -*-
"""关键点检验:game_vs_builtin_ai 第26手(羊走)前,新引擎的选择与指标。
旧引擎当时走 C3→C2,狼正招数从1暴涨到7(压力崩掉);看新引擎走什么。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import endgame
from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, pos_name,
                   apply_wolf_move, apply_sheep_move, popcount,
                   INIT_WOLVES, INIT_SHEEP)
import replay_human
from engine import Engine

endgame.load_tables()
eng = Engine()
moves = replay_human.parse(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "game_vs_builtin_ai.txt"))

w, s = INIT_WOLVES, INIT_SHEEP
hist = [(w, s)]
for i, (who, frm, to, tag) in enumerate(moves[:25], 1):
    if who == "狼":
        w, s = apply_wolf_move(w, s, frm, to)
    else:
        w, s = apply_sheep_move(w, s, frm, to)
    hist.append((w, s))

print("第26手前(羊走) 羊", popcount(s), "只")
mv, info = eng.best_move(w, s, SHEEP, history=hist)
w2, s2 = apply_sheep_move(w, s, mv[0], mv[1])
safe = eng._wolf_safe_caps(w2, s2)
b, t = eng._opp_err(w2, s2, WOLF)
ch = eng._pressure_chain(w2, s2)
print(f"新引擎: {pos_name(mv[0])}→{pos_name(mv[1])}  "
      f"安全吃={safe} 狼正招={t - b} 压力链={ch} 值={info['value']}")
print(f"(旧引擎当时: C3→C2,狼正招=7)")

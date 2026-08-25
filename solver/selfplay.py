# -*- coding: utf-8 -*-
"""自对弈:我方狼 vs 我方羊(修复前后对比羊的存活数)。
狼=吃羊优先+骗招;羊=不送子+骗招。150步封顶。"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules import (WOLF, SHEEP, INIT_WOLVES, INIT_SHEEP, popcount,
                   apply_wolf_move, apply_sheep_move, wolf_moves)
import endgame
from engine import Engine

eng = Engine()
w, s = INIT_WOLVES, INIT_SHEEP
turn = WOLF
hist = []
moves = 0
while moves < 150:
    mv, info = eng.best_move(w, s, turn, history=hist, ply_budget=150 - moves)
    if mv is None:
        break
    hist.append((w, s))
    if turn == WOLF:
        w, s = apply_wolf_move(w, s, mv[0], mv[1])
    else:
        w, s = apply_sheep_move(w, s, mv[0], mv[1])
    turn = 1 - turn
    moves += 1
    if popcount(s) <= 3:
        print(f"狼胜: 第{moves}步, 羊剩{popcount(s)}只")
        break
    if turn == WOLF and not wolf_moves(w, s):
        print(f"羊胜: 第{moves}步")
        break
else:
    print(f"150步封顶: 和棋(判狼胜), 羊剩{popcount(s)}只")
print(f"总步数={moves}")

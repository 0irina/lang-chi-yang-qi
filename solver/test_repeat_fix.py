# -*- coding: utf-8 -*-
"""重复规则回归(实战教训:game_vs_builtin_ai 第44手):
回放该局到第43手,第44手(羊走)引擎必须走 B5→B4——它是唯一和棋着法,
虽重复历史(第2次出现,合法),绝不能挑败着白送成狼胜。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import endgame
from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, pos_name,
                   apply_wolf_move, apply_sheep_move, popcount)
import replay_human
from engine import Engine

endgame.load_tables()
moves = replay_human.parse(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "game_vs_builtin_ai.txt"))
assert len(moves) == 47, len(moves)

w, s = replay_human.INIT_WOLVES, replay_human.INIT_SHEEP
hist = [(w, s)]
for i, (who, frm, to, tag) in enumerate(moves[:43], 1):
    if who == "狼":
        w, s = apply_wolf_move(w, s, frm, to)
    else:
        w, s = apply_sheep_move(w, s, frm, to)
    hist.append((w, s))

v0 = endgame.lookup(w, s, SHEEP)
assert v0 == DRAW, f"第44手前应为和棋,实际 {v0}"
# 唯一和棋着法 B5→B4 (pos 1 -> 6)
eng = Engine()
mv, info = eng.best_move(w, s, SHEEP, history=hist)
assert (mv[0], mv[1]) == (1, 6), \
    f"引擎应走 B5→B4,实际 {pos_name(mv[0])}→{pos_name(mv[1])}"
assert info["value"] == DRAW
print("第44手回归: 引擎选 B5→B4 守住和棋 OK(重复2次合法,不白送)")

# 附加:该着法走后局面在历史中已出现1次(走后=第2次出现,合法,未到第5次)
w2, s2 = apply_sheep_move(w, s, 1, 6)
cnt = hist.count((w2, s2))
assert cnt == 1, f"B5→B4 后局面历史次数应为1,实际 {cnt}"
print(f"重复次数核对: 历史已出现{cnt}次,走后第{cnt + 1}次(<=4 合法) OK")
print("RESULT: ALL OK")

# -*- coding: utf-8 -*-
"""羊方开局选招测试(开局书 + 轮换):
1) 书内局面:开局书优先——第4手(人类中心阵线)固定走书内走法;
2) 非书内开局局面:不同随机种子应选出多个同档候选(防高手背谱),
   且全部保持和棋。
"""
import random
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import endgame
from engine import Engine
from rules import (WOLF, SHEEP, DRAW, pos_name, INIT_WOLVES, INIT_SHEEP,
                   apply_wolf_move, apply_sheep_move, wolf_moves)
import opening_book

endgame.load_tables()


def wolf_draw_reply(w, s):
    for a, b, cap in wolf_moves(w, s):
        w2, s2 = apply_wolf_move(w, s, a, b)
        if endgame.lookup(w2, s2, SHEEP) == DRAW:
            return a, b, cap
    raise AssertionError("无狼和棋应手")


# ---- 1) 书内局面:开局书优先(人类中心阵线第4手) ----
w, s = INIT_WOLVES, INIT_SHEEP
w, s = apply_wolf_move(w, s, 2, 12)
w, s = apply_sheep_move(w, s, 11, 6)      # 羊2 B3→B4
w, s = apply_wolf_move(w, s, 3, 13)       # 狼3 D5→D3
assert endgame.lookup(w, s, SHEEP) == DRAW
assert (w, s) in opening_book.BOOK, "该局面应在开局书内"

eng = Engine()
eng.opening_variety = True
eng.opening_plies = 1000
picks = set()
for seed in range(40):
    eng.rng = random.Random(seed)
    mv, info = eng.best_move(w, s, SHEEP, history=((0, 0), (0, 0), (0, 0)))
    assert info["value"] == DRAW, info
    picks.add((mv[0], mv[1]))
names = sorted(f"{pos_name(a)}→{pos_name(b)}" for a, b in picks)
print("书内局面第4手(40种子):", names)
assert picks and all(mv in opening_book.BOOK[(w, s)] for mv in picks), names
print("开局书优先 OK")

# ---- 2) 非书内开局局面:轮换生效 ----
w, s = INIT_WOLVES, INIT_SHEEP
w, s = apply_wolf_move(w, s, 2, 12)
w, s = apply_sheep_move(w, s, 10, 5)      # 羊2 A3→A4 (狼和着>=2,非书内线)
w, s = apply_wolf_move(w, s, *wolf_draw_reply(w, s)[:2])
assert endgame.lookup(w, s, SHEEP) == DRAW
assert (w, s) not in opening_book.BOOK, "该局面不应在开局书内"

eng2 = Engine()
eng2.opening_variety = True
eng2.opening_plies = 1000
picks2 = set()
for seed in range(40):
    eng2.rng = random.Random(seed)
    mv, info = eng2.best_move(w, s, SHEEP, history=((0, 0), (0, 0), (0, 0)))
    assert info["value"] == DRAW, info
    picks2.add((mv[0], mv[1]))
names2 = sorted(f"{pos_name(a)}→{pos_name(b)}" for a, b in picks2)
print("非书内局面第4手(40种子):", names2)
assert len(picks2) >= 2, f"轮换未生效:40个种子只选出1手 {names2}"
print("开局轮换 OK")

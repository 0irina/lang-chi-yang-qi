# -*- coding: utf-8 -*-
"""复现:狼开局走错后(羊胜局面),分析招法 vs 候选面板第一手是否一致。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import endgame
from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, pos_name,
                   wolf_moves, apply_wolf_move, popcount,
                   INIT_WOLVES, INIT_SHEEP)
from engine import Engine

endgame.load_tables()
eng = Engine()

for frm, to, cap in wolf_moves(INIT_WOLVES, INIT_SHEEP):
    w, s = apply_wolf_move(INIT_WOLVES, INIT_SHEEP, frm, to)
    v = endgame.lookup(w, s, SHEEP)
    if v != SHEEP_WIN:
        continue
    mv, info = eng.best_move(w, s, SHEEP, history=())
    cands = eng.ranked_moves(w, s, SHEEP, history=(), raw=True,
                             score_depth=4, no_chain=True)
    first = cands[0] if cands else None
    same = (mv[0], mv[1]) == (first[0][0], first[0][1]) if first else False
    print(f"狼败着 {pos_name(frm)}→{pos_name(to)}: "
          f"best={pos_name(mv[0])}→{pos_name(mv[1])}(d={info['dist']}) "
          f"候选首={pos_name(first[0][0])}→{pos_name(first[0][1])} "
          f"{'一致' if same else '不一致!'}")

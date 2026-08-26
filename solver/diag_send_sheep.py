# -*- coding: utf-8 -*-
"""诊断 game_vs_builtin_ai:羊(引擎)每步走后——
狼"安全可吃"的着法数(safe,送子检测)、狼两回合吃子威胁(threat)、
狼正招数(wcorr)。用数据判断引擎到底是"送子"还是"没压住"。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import endgame
from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, pos_name,
                   wolf_moves, sheep_moves, apply_wolf_move, apply_sheep_move,
                   popcount, INIT_WOLVES, INIT_SHEEP)
import replay_human
from engine import Engine

endgame.load_tables()
eng = Engine()
moves = replay_human.parse(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "game_vs_builtin_ai.txt"))

w, s = INIT_WOLVES, INIT_SHEEP
tot_safe = 0
print(f"{'手':>3} {'羊招':<9} {'安全吃':>4} {'威胁':>3} {'狼正招':>4}")
for i, (who, frm, to, tag) in enumerate(moves, 1):
    if who == "狼":
        w, s = apply_wolf_move(w, s, frm, to)
        continue
    w2, s2 = apply_sheep_move(w, s, frm, to)
    safe = eng._wolf_safe_caps(w2, s2)
    thr = eng._wolf_cap_threat(w2, s2)
    b, t = eng._opp_err(w2, s2, WOLF)
    tot_safe += safe
    flag = "  <-- 送子" if safe > 0 else ""
    print(f"{i:>3} {pos_name(frm)}→{pos_name(to):<7} {safe:>4} {thr:>4} "
          f"{t - b:>4}{flag}")
    w, s = w2, s2

print(f"\n合计: 羊走后给狼'安全可吃'的着法 {tot_safe} 处")

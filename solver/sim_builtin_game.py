# -*- coding: utf-8 -*-
"""模拟:新引擎执羊 vs game_vs_builtin_ai 记录的狼着法。
羊每步由引擎选择(带历史);与记录不同即记录分歧点,随后无法继续沿
记录走狼着法即停。统计新引擎每步:安全吃(送子)、狼正招数、压力链。"""
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
eng.opening_variety = False
moves = replay_human.parse(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "game_vs_builtin_ai.txt"))

w, s = INIT_WOLVES, INIT_SHEEP
hist = [(w, s)]
print(f"{'手':>3} {'引擎羊招':<9} {'安全吃':>4} {'狼正招':>4} {'压力链':>4} "
      f"{'与记录同':>6}")
tot_safe = 0
for i, (who, frm, to, tag) in enumerate(moves, 1):
    if who == "狼":
        w, s = apply_wolf_move(w, s, frm, to)
        hist.append((w, s))
        continue
    mv, info = eng.best_move(w, s, SHEEP, history=hist)
    if mv is None or info["value"] != DRAW:
        print(f"{i:>3} 引擎无可走和棋着法/出错,停")
        break
    same = (mv[0], mv[1]) == (frm, to)
    w2, s2 = apply_sheep_move(w, s, mv[0], mv[1])
    safe = eng._wolf_safe_caps(w2, s2)
    b, t = eng._opp_err(w2, s2, WOLF)
    ch = eng._pressure_chain(w2, s2)
    tot_safe += safe
    print(f"{i:>3} {pos_name(mv[0])}→{pos_name(mv[1]):<7} {safe:>4} "
          f"{t - b:>4} {ch:>4} {'是' if same else '否*':>6}")
    if not same:
        print(f"    (记录走 {pos_name(frm)}→{pos_name(to)},此后狼着法不再适用,停止)")
        break
    w, s = w2, s2
    hist.append((w, s))

print(f"\n合计: 引擎羊走后给狼'安全可吃'的着法 {tot_safe} 处")

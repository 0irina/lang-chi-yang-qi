# -*- coding: utf-8 -*-
"""第4手(羊第2手)诊断:高手认为不该走 E3→E4,软件却一直选它。
沿引擎最优线走到第4手,枚举羊的全部候选,用强手模型 P(羊胜) 与
局面评分打分,看数据是否支持高手的说法。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, WIN_NAMES,
                   pos_name, sheep_moves, apply_wolf_move, apply_sheep_move,
                   INIT_WOLVES, INIT_SHEEP)
import endgame
from engine import Engine
import winrate
from strong_model import _eval_wolf_turn

endgame.load_tables()
eng = Engine()

# 用户给出的主线:1. 狼C5→C3 2. 羊B3→B4 3. 狼D5→D3 → 第4手羊走
w, s = INIT_WOLVES, INIT_SHEEP
line = [(WOLF, 2, 12), (SHEEP, 11, 6), (WOLF, 3, 13)]
for t, a, b in line:
    if t == WOLF:
        w, s = apply_wolf_move(w, s, a, b)
    else:
        w, s = apply_sheep_move(w, s, a, b)
print("主线:", " ".join(f"{'狼' if t==WOLF else '羊'}{pos_name(a)}→{pos_name(b)}"
                       for t, a, b in line))
print(f"第4手局面(羊走): {WIN_NAMES.get(endgame.lookup(w, s, SHEEP))}\n")

rows = []
for frm, to in sheep_moves(w, s):
    w2, s2 = apply_sheep_move(w, s, frm, to)
    v = endgame.lookup(w2, s2, WOLF)
    if v != DRAW:
        continue
    p = _eval_wolf_turn(w2, s2, 3)          # 强手模型 P(羊胜)
    sc = winrate.score_position(w2, s2, WOLF, eng=eng, depth=4)[0]
    safe = eng._wolf_safe_caps(w2, s2)
    threat = eng._wolf_cap_threat(w2, s2)
    bad = eng._opp_err(w2, s2, WOLF)[0]
    rows.append((p, sc, frm, to, safe, threat, bad))

rows.sort(key=lambda x: -x[0])
print("第4手羊方候选(按强手模型 P(羊胜) 排序):")
print(f"{'招法':>10} {'P(羊胜)':>8} {'局面评分':>8} {'安全吃子':>8} "
      f"{'吃子威胁':>8} {'败招数':>6}")
for p, sc, frm, to, safe, threat, bad in rows:
    mark = "  ← 引擎选" if (frm, to) == line[1][1:] else ""
    print(f"{pos_name(frm)}→{pos_name(to):>2} {p:>8.4f} {sc:>+8.0f} "
          f"{safe:>8} {threat:>8} {bad:>6}{mark}")
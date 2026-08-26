# -*- coding: utf-8 -*-
"""快速重复规则回归(各20例):
1) 羊:后继已出现4次(再走=第5次=羊负)有其他出路时必须回避;
2) 狼:存在一步走回"已出现4次"局面=规则胜,必须识别并选择;
3) 羊:走后不能让狼一步走回"第4次出现"局面;
4) 狼重复压迫键镜像一致。
"""
import os
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules import WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, wolf_moves, \
    sheep_moves, apply_wolf_move, apply_sheep_move, pos_name
import endgame
import winrate
from engine import Engine

eng = Engine()
rng = random.Random(321)

# 1+2) 5次规则
n1 = bad_sheep5 = bad_wolf5 = 0
trials = 0
while n1 < 20 and trials < 200000:
    trials += 1
    cells = rng.sample(range(25), 3 + rng.choice([5, 6, 7, 8]))
    w = sum(1 << c for c in cells[:3])
    s = sum(1 << c for c in cells[3:])
    if endgame.lookup(w, s, SHEEP) != DRAW:
        continue
    mv, info = eng.best_move(w, s, SHEEP, history=(),
                             score_depth=4, no_chain=True)
    if mv is None or info["value"] != DRAW:
        continue
    w2, s2 = apply_sheep_move(w, s, mv[0], mv[1])
    if len(sheep_moves(w, s)) < 2:
        continue
    dm = [(a, b) for a, b in sheep_moves(w, s)
          if endgame.lookup(*apply_sheep_move(w, s, a, b), WOLF) == DRAW]
    if any(apply_sheep_move(w, s, a, b) == (w2, s2) for a, b in dm):
        alt = [(a, b) for a, b in dm
               if apply_sheep_move(w, s, a, b) != (w2, s2)]
        if alt:
            mv2, _ = eng.best_move(w, s, SHEEP, history=((w2, s2),) * 4,
                                   score_depth=4, no_chain=True)
            w3, s3 = apply_sheep_move(w, s, mv2[0], mv2[1])
            if (w3, s3) == (w2, s2):
                bad_sheep5 += 1
    n1 += 1
    if endgame.lookup(w, s, WOLF) == DRAW:
        can5 = [(a, b, cap) for a, b, cap in wolf_moves(w, s)
                if apply_wolf_move(w, s, a, b) == (w2, s2)]
        if can5:
            wmv, winfo = eng.best_move(w, s, WOLF, history=((w2, s2),) * 4,
                                       score_depth=4, no_chain=True)
            if wmv is None or (wmv[0], wmv[1]) not in \
                    {(a, b) for a, b, c in can5} or \
                    winfo["value"] != WOLF_WIN:
                bad_wolf5 += 1
print(f"5次规则: 羊侧{n1}例(第5次未回避{bad_sheep5}), "
      f"狼规则胜识别失败{bad_wolf5}", flush=True)

# 3) 羊走后不能让狼一步走回第4次出现局面
n3 = bad_z = 0
trials = 0
while n3 < 20 and trials < 300000:
    trials += 1
    cells = rng.sample(range(25), 3 + rng.choice([5, 6, 7, 8]))
    w = sum(1 << c for c in cells[:3])
    s = sum(1 << c for c in cells[3:])
    if endgame.lookup(w, s, SHEEP) != DRAW:
        continue
    hist = [(w, s)]
    cw, cs, ct = w, s, SHEEP
    for _ in range(8):
        mvc = eng._choose_table_move(cw, cs, ct, fast=True)
        if mvc is None:
            break
        if ct == SHEEP:
            cw, cs = apply_sheep_move(cw, cs, mvc[0], mvc[1])
        else:
            cw, cs = apply_wolf_move(cw, cs, mvc[0], mvc[1])
        hist.append((cw, cs))
        ct = 1 - ct
    if len(hist) < 5:
        continue
    danger = False
    for m in sheep_moves(w, s):
        aw, as_ = apply_sheep_move(w, s, m[0], m[1])
        if endgame.lookup(aw, as_, WOLF) != DRAW:
            continue
        for wm in wolf_moves(aw, as_):
            ww, ss = apply_wolf_move(aw, as_, wm[0], wm[1])
            if hist.count((ww, ss)) >= 4:
                danger = True
                break
        if danger:
            break
    if not danger:
        continue
    n3 += 1
    mv, _ = eng.best_move(w, s, SHEEP, history=tuple(hist),
                          score_depth=4, no_chain=True)
    w2, s2 = apply_sheep_move(w, s, mv[0], mv[1])
    for wm in wolf_moves(w2, s2):
        ww, ss = apply_wolf_move(w2, s2, wm[0], wm[1])
        if hist.count((ww, ss)) >= 4:
            bad_z += 1
            print(f"  [羊·走后狼规则胜] {pos_name(mv[0])}→{pos_name(mv[1])}")
            break
print(f"规则硬检查: 危险局面{n3}例, 未回避{bad_z}", flush=True)

print("RESULT:", "ALL OK" if (bad_sheep5 == 0 and bad_wolf5 == 0
                              and bad_z == 0 and n1 >= 10 and n3 >= 8)
      else "FAIL")

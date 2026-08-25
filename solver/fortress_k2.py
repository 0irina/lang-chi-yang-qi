# -*- coding: utf-8 -*-
"""深验证 k=12 严格堡垒(16层) + 采样寻找 k=13/14 严格堡垒。"""
import random
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import endgame
from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, pos_name,
                   popcount, wolf_moves, apply_wolf_move)
import fortress_reach as FR

endgame.load_tables()

# k=12 例子(上一轮找到)
w12 = (1 << 9) | (1 << 12) | (1 << 17)
s12 = 0
for p in (0, 1, 5, 10, 11, 13, 15, 16, 19, 20, 23, 24):
    s12 |= 1 << p

t0 = time.time()
ok16 = FR.fortress_holds(w12, s12, WOLF, frozenset(), 16)
print(f"k=12 例子 16层严格验证: {'守住' if ok16 else '被攻破'} "
      f"用时={time.time()-t0:.0f}s")

rng = random.Random(20260825)
for k in (13, 14):
    found = None
    tested = 0
    for _ in range(300000):
        cells = rng.sample(range(25), 3 + k)
        w = sum(1 << c for c in cells[:3])
        s = sum(1 << c for c in cells[3:])
        if endgame.lookup(w, s, WOLF) != DRAW:
            continue
        if not FR.no_safe_caps(w, s):
            continue
        if not wolf_moves(w, s):
            continue
        tested += 1
        if FR.fortress_holds(w, s, WOLF, frozenset(), 8):
            found = (w, s)
            break
        if tested >= 500:
            break
    if found:
        w, s = found
        wpos = [pos_name(p) for p in range(25) if (w >> p) & 1]
        spos = [pos_name(p) for p in range(25) if (s >> p) & 1]
        print(f"k={k}: 找到严格堡垒(测试{tested}个)")
        print(f"   狼位: {wpos}  羊位: {spos}")
    else:
        print(f"k={k}: 采样{tested}个无安全吃子局面,无一通过")

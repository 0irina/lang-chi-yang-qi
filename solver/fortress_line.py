# -*- coding: utf-8 -*-
"""堡垒线 + 深度复核:深度12搜索出主变线,找到羊进入堡垒的叶子局面,
再用 16 层深搜复核该堡垒是否会被狼在更深处攻破。
同时打印叶子局面的破解表值(和棋=羊无法强胜,证明"13只堡垒≠羊赢")。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import endgame
from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, WIN_NAMES,
                   pos_name, popcount, apply_wolf_move, apply_sheep_move,
                   INIT_WOLVES, INIT_SHEEP)
from fortress_reach import (search, TT, fortress_holds, fortress_ok,
                            NODES as _N)

endgame.load_tables()

t0 = time.time()
ans = search(INIT_WOLVES, INIT_SHEEP, WOLF, frozenset(), 12, 0, 16)
print(f"羊可保住 = {ans}  用时={time.time()-t0:.1f}s\n")

w, s, t = INIT_WOLVES, INIT_SHEEP, WOLF
leaf = None
steps = 0
print("主变线:")
while steps < 40:
    r = TT.get((w, s, t))
    if r is None or r[1] is None:
        break
    m = r[1]
    if t == WOLF:
        w2, s2 = apply_wolf_move(w, s, m[0], m[1])
        cap = popcount(s) > popcount(s2)
        print(f"  狼 {pos_name(m[0])}→{pos_name(m[1])}{' 吃' if cap else ''}")
        w, s = w2, s2
    else:
        w, s = apply_sheep_move(w, s, m[0], m[1])
        print(f"  羊 {pos_name(m[0])}→{pos_name(m[1])}")
        if fortress_ok(w, s):
            leaf = (w, s)
            print(f"  >>> 进入堡垒:羊剩 {popcount(s)} 只")
            break
    t = 1 - t
    steps += 1

if leaf is not None:
    wl, sl = leaf
    v = endgame.lookup(wl, sl, WOLF)
    print(f"\n堡垒叶子局面表值 = {WIN_NAMES.get(v)}")
    print(f"羊位: {[pos_name(p) for p in range(25) if (sl>>p)&1]}")
    print(f"狼位: {[pos_name(p) for p in range(25) if (wl>>p)&1]}")
    t1 = time.time()
    ok16 = fortress_holds(wl, sl, WOLF, frozenset(), 16)
    print(f"16层深搜复核该堡垒: {'守住' if ok16 else '被攻破!'}  "
          f"用时={time.time()-t1:.1f}s")

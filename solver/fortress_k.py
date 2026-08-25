# -*- coding: utf-8 -*-
"""严格堡垒存在性:k=8..12 采样无立即安全吃子的和棋局面,
用严格堡垒验证(狼任一安全吃子即攻破,允许狼来回走)逐一测试。
回答"狼被控制在小范围时羊最多剩几只"。"""
import random
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import endgame
from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, pos_name,
                   popcount, wolf_moves, sheep_moves, apply_wolf_move,
                   apply_sheep_move)
import fortress_reach as FR

endgame.load_tables()
rng = random.Random(20260825)


def has_move(w, s):
    return len(wolf_moves(w, s)) > 0


for k in range(8, 13):
    t0 = time.time()
    found = None
    tested = 0
    for _ in range(200000):
        cells = rng.sample(range(25), 3 + k)
        w = sum(1 << c for c in cells[:3])
        s = sum(1 << c for c in cells[3:])
        if endgame.lookup(w, s, WOLF) != DRAW:
            continue
        if not FR.no_safe_caps(w, s):
            continue
        if not has_move(w, s):
            continue  # 狼全被围死=羊胜,不是堡垒
        tested += 1
        if FR.fortress_holds(w, s, WOLF, frozenset(), 8):
            found = (w, s)
            break
        if tested >= 300:
            break
    if found:
        w, s = found
        wpos = [pos_name(p) for p in range(25) if (w >> p) & 1]
        spos = [pos_name(p) for p in range(25) if (s >> p) & 1]
        print(f"k={k}: 存在严格堡垒! (测试{tested}个无安全吃子局面, "
              f"用时{time.time()-t0:.0f}s)")
        print(f"   狼位: {wpos}  狼可走步数={len(wolf_moves(w, s))}")
        print(f"   羊位: {spos}")
    else:
        print(f"k={k}: 采样{tested}个无安全吃子局面,无一通过严格堡垒"
              f" (用时{time.time()-t0:.0f}s)")

# -*- coding: utf-8 -*-
"""堡垒研究:满足以下条件的局面(狼3只,羊k只):
  1) 和棋;2) 当前狼无任何"安全吃子"(吃即羊胜或无吃);
  3) 狼无论怎么走(非败),羊都有不重复的变招继续维持该性质 → 狼永远吃不到羊。
统计每个 k 是否存在此类局面,找出最多能保几只羊。"""
import random
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, popcount,
                   wolf_moves, sheep_moves, apply_wolf_move, apply_sheep_move,
                   pos_name)
import endgame

endgame.load_tables()
rng = random.Random(20260824)


def no_safe_caps(w, s):
    for frm, to, cap in wolf_moves(w, s):
        if not cap:
            continue
        w2, s2 = apply_wolf_move(w, s, frm, to)
        if popcount(s2) <= 3 or endgame.lookup(w2, s2, SHEEP) != SHEEP_WIN:
            return False
    return True


def fortress_holds(w, s, turn, seen, depth):
    """狼想吃到羊(走到羊<=3或吃到任意一只);羊想无限维持。
    turn=当前走子方;seen={(w,s,turn)} 羊侧防重复。深度内狼吃不到=成立。"""
    if popcount(s) <= 3:
        return False
    if depth <= 0:
        return True
    key = (w, s, turn)
    if key in seen:
        return True  # 循环=狼没吃到,按和棋(羊侧靠外层防重复)
    seen = seen | {key}
    if turn == WOLF:
        for frm, to, cap in wolf_moves(w, s):
            w2, s2 = apply_wolf_move(w, s, frm, to)
            if popcount(s2) <= 3:
                return False                    # 狼直接吃剩3只,失守
            if endgame.lookup(w2, s2, SHEEP) == SHEEP_WIN:
                continue                        # 毒吃狼不会走
            if not fortress_holds(w2, s2, SHEEP, seen, depth - 1):
                return False
        return True
    else:
        for frm, to in sheep_moves(w, s):
            w2, s2 = apply_sheep_move(w, s, frm, to)
            if (w2, s2, WOLF) in seen:
                continue                        # 羊不能重复(同方局面)
            if fortress_holds(w2, s2, WOLF, seen, depth - 1):
                return True
        return False


# ---- 阶段1:采样找"当前无安全吃子"的和棋局面 ----
found = {}
for k in range(4, 16):
    for _ in range(60000):
        cells = rng.sample(range(25), 3 + k)
        w = sum(1 << c for c in cells[:3])
        s = sum(1 << c for c in cells[3:])
        if endgame.lookup(w, s, WOLF) != DRAW:
            continue
        if no_safe_caps(w, s):
            found[k] = (w, s)
            break

print("阶段1:采样中各 k 是否存在'当前无安全吃子'的和棋局面")
for k in range(4, 16):
    if k in found:
        w, s = found[k]
        wpos = [pos_name(p) for p in range(25) if (w >> p) & 1]
        print(f"  k={k}: 找到(狼位 {wpos})")
    else:
        print(f"  k={k}: 6万次采样未找到")

# ---- 阶段2:对找到的最大 k 做堡垒验证 ----
for k in sorted(found, reverse=True):
    w, s = found[k]
    ok = fortress_holds(w, s, WOLF, frozenset(), 14)
    print(f"\nk={k} 局面堡垒验证(深度14): {'成立(狼限内吃不到)' if ok else '被攻破'}")
    if ok:
        print(f"  狼位: {[pos_name(p) for p in range(25) if (w>>p)&1]}")
        print(f"  羊位: {[pos_name(p) for p in range(25) if (s>>p)&1]}")
    break

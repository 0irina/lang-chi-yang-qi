# -*- coding: utf-8 -*-
"""定位 game_vs_builtin_ai 第26手的真实走法:穷举所有合法羊走法,
检查后续 27..47 手是否全部合法;并输出每个可行分支在第44手的状态与书成员。"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import endgame
from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW,
                   pos_name, wolf_moves, sheep_moves,
                   apply_wolf_move, apply_sheep_move, popcount,
                   INIT_WOLVES, INIT_SHEEP)
import opening_book
import opening_book2

endgame.load_tables()


def cell(s):
    return (ord(s[0]) - 65) + (5 - int(s[1])) * 5


def parse(path):
    moves = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        m = re.match(r"^(\d+)\.\s*(.*)$", line)
        if not m:
            continue
        body = m.group(2)
        parts = body.split()
        if len(parts) < 2 or parts[0] not in ("狼", "羊"):
            continue
        who = parts[0]
        a, b = parts[1].replace("吃", "").split("→")
        moves.append((who, cell(a), cell(b), "吃" in body))
    return moves


moves = parse(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "game_vs_builtin_ai.txt"))
assert len(moves) == 47, len(moves)

# 前25手固定
w, s = INIT_WOLVES, INIT_SHEEP
for i, (who, a, b, cap) in enumerate(moves[:25], 1):
    if who == "狼":
        w, s = apply_wolf_move(w, s, a, b)
    else:
        w, s = apply_sheep_move(w, s, a, b)

tail = moves[26:]

ok_branches = []
for (a, b) in sheep_moves(w, s):
    w2, s2 = apply_sheep_move(w, s, a, b)
    if endgame.lookup(w2, s2, WOLF) != DRAW:
        continue  # 第26手必须是和棋着法(前25手全是和棋)
    cw, cs = w2, s2
    legal = True
    for who, ta, tb, tcap in tail:
        if who == "狼":
            if not any((x, y) == (ta, tb) for x, y, c2 in wolf_moves(cw, cs)):
                legal = False
                break
            cw, cs = apply_wolf_move(cw, cs, ta, tb)
        else:
            if not any((x, y) == (ta, tb) for x, y in sheep_moves(cw, cs)):
                legal = False
                break
            cw, cs = apply_sheep_move(cw, cs, ta, tb)
    if legal:
        ok_branches.append((a, b))

print("第26手可行候选(走完后 27..47 全合法):")
for a, b in ok_branches:
    print(f"  {pos_name(a)}→{pos_name(b)}")

# 对每个可行分支,查第44手状态
for a26, b26 in ok_branches:
    cw, cs = INIT_WOLVES, INIT_SHEEP
    for i, (who, a, b, cap) in enumerate(moves[:25], 1):
        if who == "狼":
            cw, cs = apply_wolf_move(cw, cs, a, b)
        else:
            cw, cs = apply_sheep_move(cw, cs, a, b)
    cw, cs = apply_sheep_move(cw, cs, a26, b26)
    for who, ta, tb, tcap in tail:
        if who == "狼":
            cw, cs = apply_wolf_move(cw, cs, ta, tb)
        else:
            cw, cs = apply_sheep_move(cw, cs, ta, tb)
    # 第44手前状态 = 回退:重新走一遍并在第43手后停下
    cw, cs = INIT_WOLVES, INIT_SHEEP
    for i, (who, a, b, cap) in enumerate(moves[:25], 1):
        if who == "狼":
            cw, cs = apply_wolf_move(cw, cs, a, b)
        else:
            cw, cs = apply_sheep_move(cw, cs, a, b)
    cw, cs = apply_sheep_move(cw, cs, a26, b26)
    seq = moves[26:43]
    for who, ta, tb, tcap in seq:
        if who == "狼":
            cw, cs = apply_wolf_move(cw, cs, ta, tb)
        else:
            cw, cs = apply_sheep_move(cw, cs, ta, tb)
    v0 = endgame.lookup(cw, cs, SHEEP)
    in1 = (cw, cs) in opening_book.BOOK
    in2 = (cw, cs) in opening_book2.BOOK2
    e1 = opening_book.BOOK.get((cw, cs))
    e2 = opening_book2.BOOK2.get((cw, cs))
    dr = [m for m in sheep_moves(cw, cs)
          if endgame.lookup(*apply_sheep_move(cw, cs, m[0], m[1]), WOLF)
          == DRAW]
    hist = set()
    hw, hs = INIT_WOLVES, INIT_SHEEP
    hist.add((hw, hs))
    for i, (who, a, b, cap) in enumerate(moves[:25], 1):
        if who == "狼":
            hw, hs = apply_wolf_move(hw, hs, a, b)
        else:
            hw, hs = apply_sheep_move(hw, hs, a, b)
        hist.add((hw, hs))
    hw, hs = apply_sheep_move(hw, hs, a26, b26)
    hist.add((hw, hs))
    for who, ta, tb, tcap in seq:
        if who == "狼":
            hw, hs = apply_wolf_move(hw, hs, ta, tb)
        else:
            hw, hs = apply_sheep_move(hw, hs, ta, tb)
        hist.add((hw, hs))
    rep_draw = [m for m in dr
                if apply_sheep_move(cw, cs, m[0], m[1]) in hist]
    print(f"--- 26={pos_name(a26)}→{pos_name(b26)}: "
          f"第44手前 值={v0} 主选={in1}({e1}) 次选={in2}({e2}) "
          f"和着={[f'{pos_name(a)}→{pos_name(b)}' for a, b in dr]} "
          f"其中重复={[f'{pos_name(a)}→{pos_name(b)}' for a, b in rep_draw]}")

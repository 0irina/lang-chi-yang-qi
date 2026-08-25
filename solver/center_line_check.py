# -*- coding: utf-8 -*-
"""细节诊断:对指定手数前的局面,打印棋盘 + 走子方全部着法价值。
用于展示"中心阵"形态与"唯一正招"走廊。
用法: python center_line_check.py <谱文件> <手数1> <手数2> ...
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import endgame
from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW,
                   WIN_NAMES, pos_name, wolf_moves, sheep_moves,
                   apply_wolf_move, apply_sheep_move, popcount,
                   INIT_WOLVES, INIT_SHEEP)

SRC = sys.argv[1]
WANT = [int(x) for x in sys.argv[2:]]


def parse(path):
    moves = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^(\d+)\.\s*(.*)$", line)
            if m:
                line = m.group(2)
            parts = line.split()
            if len(parts) < 2 or parts[0] not in ("狼", "羊"):
                continue
            who = parts[0]
            mv = parts[1].replace("->", "→")
            a, b = mv.split("→")

            def cell(s):
                col = ord(s[0]) - 65
                r0 = 5 - int(s[1])
                return r0 * 5 + col

            moves.append((who, cell(a), cell(b)))
    return moves


def board_str(w, s):
    out = []
    for r in range(5):
        cells = []
        for c in range(5):
            p = r * 5 + c
            if (w >> p) & 1:
                cells.append("W")
            elif (s >> p) & 1:
                cells.append("S")
            else:
                cells.append(".")
        out.append("".join(cells))
    return "\n".join(out)


moves = parse(SRC)
endgame.load_tables()
w, s = INIT_WOLVES, INIT_SHEEP

for i, (who, frm, to) in enumerate(moves, 1):
    if i in WANT:
        turn = WOLF if who == "狼" else SHEEP
        print("=" * 62)
        print(f"第{i}手前({who}走) 羊{popcount(s)}只  狼位:",
              " ".join(pos_name(p) for p in range(25) if (w >> p) & 1))
        print(board_str(w, s))
        v0 = endgame.lookup(w, s, turn)
        print(f"局面真实值: {WIN_NAMES[v0]} (dist={endgame.lookup_dist(w, s, turn)})")
        if who == "狼":
            rows = []
            for a, b, cap in wolf_moves(w, s):
                w2, s2 = apply_wolf_move(w, s, a, b)
                if popcount(s2) <= 3:
                    vv, dd = WOLF_WIN, 0
                else:
                    vv = endgame.lookup(w2, s2, SHEEP)
                    dd = endgame.lookup_dist(w2, s2, SHEEP)
                rows.append((a, b, cap, vv, dd))
            rows.sort(key=lambda r: (r[3] != WOLF_WIN, r[3] != DRAW, r[3] != SHEEP_WIN))
            for a, b, cap, vv, dd in rows:
                print(f"  {pos_name(a)}→{pos_name(b)}"
                      f"{'吃' if cap else '':<2} -> {WIN_NAMES[vv]}(d={dd})")
        else:
            rows = []
            for a, b in sheep_moves(w, s):
                w2, s2 = apply_sheep_move(w, s, a, b)
                vv = endgame.lookup(w2, s2, WOLF)
                dd = endgame.lookup_dist(w2, s2, WOLF)
                rows.append((a, b, vv, dd))
            rows.sort(key=lambda r: (r[2] != SHEEP_WIN, r[2] != DRAW, r[2] != WOLF_WIN))
            for a, b, vv, dd in rows:
                print(f"  {pos_name(a)}→{pos_name(b)} -> {WIN_NAMES[vv]}(d={dd})")
        print()
    if who == "狼":
        w, s = apply_wolf_move(w, s, frm, to)
    else:
        w, s = apply_sheep_move(w, s, frm, to)

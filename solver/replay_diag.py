# -*- coding: utf-8 -*-
"""回放诊断:用户棋谱逐手核对 AI执狼 每一步的真实值与限步利用情况。
用与用户软件包相同的(旧)表;同时给出修复后引擎的同局面选择。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, WIN_NAMES,
                   pos_name, apply_wolf_move, apply_sheep_move, popcount,
                   INIT_WOLVES, INIT_SHEEP)
import endgame
from engine import Engine

NOTATION = """狼 C5→C3 吃
羊 D3→D4
狼 B5→B3 吃
羊 E3→D3
狼 B3→B4
羊 D4→C4
狼 B4→A4
羊 A3→B3
狼 A4→C4 吃
羊 B3→B4
狼 D5→D3 吃
羊 B2→B3
狼 C4→D4
羊 B4→C4
狼 D4→E4
羊 C4→D4
狼 C3→C4
羊 B3→B4
狼 C4→C2 吃
羊 B1→B2
狼 E4→E2 吃
羊 C1→B1
狼 C2→C3
羊 B2→C2
狼 C3→B3
羊 B1→B2
狼 B3→A3
羊 A1→B1
狼 D3→C3
羊 B2→B3
狼 C3→C4
羊 C2→B2
狼 E2→E3
羊 D2→D3
狼 E3→E1 吃
羊 B1→C1
狼 C4→C3
羊 B2→C2
狼 A3→A4
羊 A2→A3
狼 E1→E2
羊 D1→D2
狼 A4→A5
羊 A3→A4
狼 A5→B5
羊 C1→D1
狼 B5→A5
羊 D4→C4
狼 A5→B5
羊 D3→D4
狼 C3→D3
羊 B3→C3
狼 E2→E3
羊 A4→A5
狼 B5→C5
羊 A5→B5
狼 E3→E4
羊 C2→C1
狼 E4→E5
羊 D4→E4
狼 C5→D5
羊 B5→A5
狼 D5→C5
羊 A5→A4
狼 E5→D5
羊 E4→D4
狼 C5→B5
羊 C1→C2
狼 B5→C5
羊 C2→B2
狼 C5→B5
羊 C3→C2
狼 B5→C5
羊 D4→E4
狼 D5→D4
羊 D1→C1
狼 D3→C3
羊 D2→D3
狼 C5→B5"""


def parse(ntext):
    moves = []
    for line in ntext.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if parts[0] not in ("狼", "羊"):
            continue
        who = parts[0]
        a, b = parts[1].split("→")
        col = ord(a[0]) - 65
        r0 = 5 - int(a[1])
        frm = r0 * 5 + col
        col = ord(b[0]) - 65
        r0 = 5 - int(b[1])
        to = r0 * 5 + col
        moves.append((who, frm, to))
    return moves


moves = parse(NOTATION)
assert len(moves) == 79, len(moves)
eng = Engine()

w, s = INIT_WOLVES, INIT_SHEEP
print(f"{'手数':>4} {'局面值':>5} {'走的招':>12} {'走后值':>5} "
      f"{'d':>3} {'预算':>4} {'限步利用?':>7} {'修复后引擎会走':>14}")
print("-" * 88)
exploits = 0
blunders = 0
diffs = 0
for i, (who, frm, to) in enumerate(moves, 1):
    if who == "羊":
        w, s = apply_sheep_move(w, s, frm, to)
        continue
    v0 = endgame.lookup(w, s, WOLF)
    budget = 150 - (i - 1)
    w2, s2 = apply_wolf_move(w, s, frm, to)
    rv = endgame.lookup(w2, s2, SHEEP)
    rd = endgame.lookup_dist(w2, s2, SHEEP)
    is_exploit = (v0 in (DRAW, WOLF_WIN) and rv == SHEEP_WIN
                  and rd >= 0 and rd > budget)
    is_blunder = (v0 in (DRAW, WOLF_WIN) and rv == SHEEP_WIN
                  and rd >= 0 and rd <= budget)
    if is_exploit:
        exploits += 1
    if is_blunder:
        blunders += 1
    mv_fix, info = eng.best_move(w, s, WOLF, ply_budget=budget)
    fix_str = f"{pos_name(mv_fix[0])}→{pos_name(mv_fix[1])}"
    fix_same = (mv_fix[0], mv_fix[1]) == (frm, to)
    if not fix_same:
        diffs += 1
    flag = ("利用!" if is_exploit else ("败招!" if is_blunder else ""))
    print(f"{i:>4} {WIN_NAMES.get(v0):>5} "
          f"{pos_name(frm)}→{pos_name(to):>2} {WIN_NAMES.get(rv):>5} "
          f"{rd:>3} {budget:>4} {flag:>7} "
          f"{fix_str + ('(同)' if fix_same else '(不同!)'):>14}")
    w, s = w2, s2

print("-" * 88)
print(f"限步利用(走后显示羊胜): {exploits} 手")
print(f"真败招(限内能赢还走):   {blunders} 手")
print(f"修复后引擎与旧引擎选招不同: {diffs} 手")
print(f"终局局面: 狼 {bin(w).count('1')}只 羊 {popcount(s)}只 "
      f"局面值={WIN_NAMES.get(endgame.lookup(w, s, WOLF))}")

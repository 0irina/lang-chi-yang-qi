# -*- coding: utf-8 -*-
"""诊断:探针线沿途局面在主选/次选书中的覆盖情况。"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import endgame
from rules import (WOLF, SHEEP, DRAW, pos_name,
                   apply_wolf_move, apply_sheep_move,
                   INIT_WOLVES, INIT_SHEEP)
import opening_book
import opening_book2

endgame.load_tables()
print("主选条目数:", len(opening_book.BOOK),
      " 次选条目数:", len(opening_book2.BOOK2))


def cell(s):
    return (ord(s[0]) - 65) + (5 - int(s[1])) * 5


line = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "dfs_probe_report.txt"),
            encoding="utf-8").read().strip().splitlines()[-1]
w, s = apply_wolf_move(INIT_WOLVES, INIT_SHEEP, 2, 12)
toks = [t for t in line.split()
        if t.startswith("狼") or t.startswith("羊")]
if toks and toks[0].startswith("狼C5→C3"):
    toks = toks[1:]
n_sheep = 0
for t in toks:
    who = t[0]
    mv = re.sub(r"\(正招\d\)", "", t[1:]).replace("吃", "")
    a, b = mv.split("→")
    a, b = cell(a), cell(b)
    if who == "羊":
        n_sheep += 1
        if (w, s) in opening_book.BOOK:
            tag = "P"
        elif (w, s) in opening_book2.BOOK2:
            tag = "S"
        else:
            tag = "-"
        print(f"S{n_sheep:>2} [{tag}] {pos_name(a)}->{pos_name(b)}")
        w, s = apply_sheep_move(w, s, a, b)
    else:
        w, s = apply_wolf_move(w, s, a, b)

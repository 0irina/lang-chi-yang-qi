# -*- coding: utf-8 -*-
"""AI 败招审计(过渡版:旧表 + 羊剩3只即胜覆盖层)。

目标:定位用户报告的"AI执狼在和棋局面走出变羊胜的招"问题。

【新设计】限步规则只是终局条件,绝不参与选招:
  - 狼方:真实羊胜线一律避开(走后局面显示羊胜 = 败招,必须为0);
  - 羊方:和棋局面不可能走到羊胜(和棋的定义),选到狼胜后继 = 败招,必须为0;
  - 羊胜局面羊走最快线(即使限内杀不完),这是刻意行为,不算bug。

检查项(狼回合与羊回合):
  A. 非羊胜局面选中"真实=羊胜"的后继 → 真败招(BUG,必须为0)
  B. 羊方和棋局面选中"真实=狼胜"的后继 → 真败招(BUG,必须为0)
  C. 箭头用 _choose_table_move 与实际 best_move 不一致(必须为0)
  D. 同局面不同预算选招不同(新设计下应为0;非0=预算仍在影响选招)
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, pos_name,
                   wolf_moves, sheep_moves, apply_wolf_move, apply_sheep_move,
                   popcount)
import endgame
from engine import Engine

eng = Engine()
rng = random.Random(20260823)

BUG = 0          # 真败招:d<=预算仍走羊胜后继
LEGIT = 0        # 限步规则:走后继显示羊胜但d>预算
MISMATCH = 0     # 箭头与实走不一致
INTERMIT = 0     # 同局面不同预算选不同招
n = 0
budgets = (5, 10, 20, 50, 150)

trials = 0
while n < 4000 and trials < 400000:
    trials += 1
    k = rng.choice([4, 5, 6, 7, 8])
    cells = rng.sample(range(25), 3 + k)
    w = sum(1 << c for c in cells[:3])
    s = sum(1 << c for c in cells[3:])
    if popcount(s) <= 3:
        continue
    for turn in (WOLF, SHEEP):
        v0 = endgame.lookup(w, s, turn)
        if v0 not in (DRAW, WOLF_WIN, SHEEP_WIN):
            continue
        if turn == WOLF and not wolf_moves(w, s):
            continue
        if turn == SHEEP and not sheep_moves(w, s):
            continue
        n += 1
        picks = {}
        for b in budgets:
            mv, info = eng.best_move(w, s, turn, history=(), ply_budget=b)
            if mv is None:
                continue
            if turn == WOLF:
                w2, s2 = apply_wolf_move(w, s, mv[0], mv[1])
            else:
                w2, s2 = apply_sheep_move(w, s, mv[0], mv[1])
            rv = endgame.lookup(w2, s2, WOLF if turn == SHEEP else SHEEP)
            rd = endgame.lookup_dist(w2, s2, WOLF if turn == SHEEP else SHEEP)
            picks[b] = (mv, rv, rd)
        if len(picks) < 2:
            continue
        # 不同预算不同选招 = 间歇性来源
        moves_set = {(m[0][0], m[0][1]) for m in picks.values()}
        if len(moves_set) > 1:
            INTERMIT += 1
        # 逐预算分类:任何非羊胜局面选中"真实=羊胜"的后继 = 真败招
        for b, (mv, rv, rd) in picks.items():
            if v0 in (DRAW, WOLF_WIN) and rv == SHEEP_WIN:
                BUG += 1
                if BUG <= 8:
                    print(f"[真败招] {('狼' if turn==WOLF else '羊')}走 "
                          f"v0={v0} 预算={b} 选中后继=羊胜 d={rd} mv="
                          f"{pos_name(mv[0])}→{pos_name(mv[1])}")
        # 用 150 预算作为"AI实际走法"(常规对局)
        mv, rv, rd = picks[150]
        # 羊回合:和棋局面选中狼胜后继 = 真败招(限步不会把和棋升级成狼胜)
        if turn == SHEEP and v0 == DRAW and rv == WOLF_WIN:
            BUG += 1
            if BUG <= 8:
                print(f"[真败招·羊] v0=DRAW 选中后继=狼胜 d={rd} mv="
                      f"{pos_name(mv[0])}→{pos_name(mv[1])}")
        # 箭头一致性
        tmv = eng._choose_table_move(w, s, turn)
        if tmv is not None and (tmv[0], tmv[1]) != (mv[0], mv[1]):
            MISMATCH += 1

print(f"\n抽样 {n} 个局面(狼/羊回合, k=4..8)")
print(f"真败招 BUG        : {BUG}   (必须为0)")
print(f"箭头与实际不一致  : {MISMATCH}   (必须为0)")
print(f"同局面不同预算不同招: {INTERMIT}  (新设计下应为0)")
print("RESULT:", "PASS" if BUG == 0 and MISMATCH == 0 else "FAIL")

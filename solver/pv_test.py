# -*- coding: utf-8 -*-
"""无头测试:验证 GUI 新的 PV 箭头链逻辑(当前方最佳->对方应对->...)。
不启动 tkinter,只测 _pv_moves 的引擎部分与合法性。"""
import random
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, INIT_WOLVES,
                   INIT_SHEEP, popcount, wolf_moves, sheep_moves,
                   apply_wolf_move, apply_sheep_move)
import endgame
from engine import Engine

eng = Engine()


def pv_moves(w, s, turn, n=4):
    pv = []
    while len(pv) < n:
        if popcount(s) <= 3:
            break
        if turn == WOLF:
            if not wolf_moves(w, s):
                break
            mv = eng._choose_table_move(w, s, WOLF)
            frm, to, cap, _v, _d = mv[:5]
            w2, s2 = apply_wolf_move(w, s, frm, to)
        else:
            if not sheep_moves(w, s):
                break
            mv = eng._choose_table_move(w, s, SHEEP)
            frm, to, cap, _v, _d = mv[:5]
            w2, s2 = apply_sheep_move(w, s, frm, to)
        pv.append((frm, to, cap))
        w, s, turn = w2, s2, 1 - turn
        if popcount(s) <= 3:
            break
    return pv


def check(name, cond, detail=""):
    print(("[OK ] " if cond else "[FAIL] ") + name + (f" {detail}" if detail else ""))


# 1) 初始局面:狼先吃中羊,之后轮到羊,羊的应对必须在"吃后局面"合法
w, s = INIT_WOLVES, INIT_SHEEP
pv = pv_moves(w, s, WOLF)
print("初始PV:", pv)
check("初始PV第1手=中心吃羊", pv[0] == (2, 12, True), f"(got {pv[0]})")
w1, s1 = apply_wolf_move(w, s, pv[0][0], pv[0][1])
check("第2手是羊方", pv[1][2] == False and ((s1 >> pv[1][0]) & 1) == 1,
      f"(got {pv[1]})")
# 交替性
turn = WOLF
ok = True
for i, mv in enumerate(pv):
    who = "狼" if turn == WOLF else "羊"
    if turn != (WOLF if i % 2 == 0 else SHEEP):
        ok = False
    turn = 1 - turn
check("PV双方严格交替", ok)

# 2) 随机狼胜局面:PV链应通向终局(羊<=2)或到达4步
# 2) 随机狼胜局面:PV链应合法,且沿链到达终局的步数 == 距离表 d 值
rng = random.Random(7)
n_ok = n_bad = 0
legal = True
for _ in range(8000):
    k = rng.choice([4, 5, 6])
    cells = rng.sample(range(25), 3 + k)
    w = sum(1 << c for c in cells[:3])
    s = sum(1 << c for c in cells[3:])
    if endgame.lookup(w, s, WOLF) != WOLF_WIN:
        continue
    d0 = endgame.lookup_dist(w, s, WOLF)
    pv = pv_moves(w, s, WOLF, n=200)
    ww, ss, tt = w, s, WOLF
    plies = 0
    for frm, to, cap in pv:
        if tt == WOLF:
            if not any((m[0] == frm and m[1] == to) for m in wolf_moves(ww, ss)):
                legal = False
                break
            ww, ss = apply_wolf_move(ww, ss, frm, to)
        else:
            if not any((m[0] == frm and m[1] == to) for m in sheep_moves(ww, ss)):
                legal = False
                break
            ww, ss = apply_sheep_move(ww, ss, frm, to)
        tt = 1 - tt
        plies += 1
        if popcount(ss) <= 3:
            break
    if not legal:
        print("  非法PV:", pv)
        break
    if popcount(ss) <= 2:
        # 以吃子终局:距离表约定 d = 步数 - 1(种子把"吃子前一步"记 0)
        ok = (plies - 1 == d0)
    else:
        # 以羊无路可走终局:终局态本身记 d=0, d == 步数
        ok = (plies == d0)
    if ok:
        n_ok += 1
    else:
        n_bad += 1
        if n_bad <= 5:
            print(f"  步数不符: d={d0} 实际={plies} pv={pv[:6]}")
check("所有狼胜局面PV链全程合法", legal)
check(f"沿PV链到达终局的步数 == 距离表d(按约定) ({n_ok}个一致, 不符{n_bad}个)",
      n_bad == 0 and n_ok > 1000)

# 3) 和棋局面:PV链能出4步
pv0 = pv_moves(INIT_WOLVES, INIT_SHEEP, WOLF)
check("和棋初始局面PV链>=3步", len(pv0) >= 3, f"(len={len(pv0)})")
print("RESULT: DONE")

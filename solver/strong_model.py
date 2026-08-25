# -*- coding: utf-8 -*-
"""强手模型评估(方向B):模拟"人类高手"对手,计算羊方各候选招的实际期望胜率。

高手模型(狼方):
  - 以 P_BEST=0.85 概率走出引擎最优招;
  - 其余概率按"显眼度"分配到各合法走法:
      salience = 3(吃子) / 2(走向中心) / 1(其他) / 0.4(退避、远离中心);
    唯一应手局面(只有一步不败)时,那步的"可发现性"再打 0.6 折(高手也常漏冷着);
  - 走错一步(落到羊胜)即判羊胜;仍和棋则继续下一层。
羊方:始终按引擎最优走(我们评估的是羊的选招,羊自己完美)。
深度:4 回合(狼-羊-狼-羊),超出则按和棋=羊输计 0。
输出:羊方开局各候选招的期望胜率,并与当前引擎实际选择对比。
"""
import os
import sys
from functools import lru_cache

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, pos_name,
                   popcount, wolf_moves, sheep_moves, apply_wolf_move,
                   apply_sheep_move, INIT_WOLVES, INIT_SHEEP)
import endgame
from engine import Engine

endgame.load_tables()
eng = Engine()
P_BEST = 0.85
CENTER_DIST = {(r, c): max(abs(r - 2), abs(c - 2)) for r in range(5)
               for c in range(5)}


def salience_wolf(w, s, frm, to, cap):
    """狼这步的显眼度:吃子3 / 走向中心2 / 原地或远离中心0.4 / 一般1"""
    if cap:
        return 3.0
    d1 = CENTER_DIST[(frm // 5, frm % 5)]
    d2 = CENTER_DIST[(to // 5, to % 5)]
    if d2 < d1:
        return 2.0
    if d2 > d1:
        return 0.4
    return 1.0


def wolf_distribution(w, s):
    """返回 [(move, prob), ...] 高手模型下狼的走法概率分布"""
    moves = wolf_moves(w, s)
    if not moves:
        return []

    def rank(v):  # 狼视角:狼胜0 < 和棋1 < 羊胜2
        return 0 if v == WOLF_WIN else (1 if v == DRAW else 2)

    best_mv = None
    best_r = None
    cats = []
    for frm, to, cap in moves:
        w2, s2 = apply_wolf_move(w, s, frm, to)
        if popcount(s2) <= 3:
            v = WOLF_WIN
        else:
            v = endgame.lookup(w2, s2, SHEEP)
        cats.append((frm, to, cap, v))
        r = rank(v)
        if best_r is None or r < best_r:
            best_r, best_mv = r, (frm, to, cap)
    # 唯一不败应手检测
    nondraw = [c for c in cats if c[3] != SHEEP_WIN]
    unique = len(nondraw) == 1
    dist = {}
    for frm, to, cap, v in cats:
        sal = salience_wolf(w, s, frm, to, cap)
        if unique and v != SHEEP_WIN:
            sal *= 0.6   # 高手也容易漏的唯一冷着
        if (frm, to, cap) == best_mv:
            dist[(frm, to, cap)] = P_BEST
        else:
            dist[(frm, to, cap)] = sal
    # 非最优部分按显眼度归一化占 1-P_BEST
    tot_other = sum(p for m, p in dist.items() if m != best_mv)
    out = []
    for m, p in dist.items():
        if m == best_mv:
            out.append((m, p))
        elif tot_other > 0:
            out.append((m, p / tot_other * (1 - P_BEST)))
    return out


def eval_sheep_move(w, s, depth=4):
    """评估:羊在当前局面走"引擎最优"后的期望胜率;狼按高手模型走。
    返回 P(羊胜)。"""
    mv = eng._choose_table_move(w, s, SHEEP)
    if mv is None:
        return 0.0
    w2, s2 = apply_sheep_move(w, s, mv[0], mv[1])
    return _eval_wolf_turn(w2, s2, depth - 1)


def _eval_wolf_turn(w, s, depth):
    """轮到狼(高手模型),返回羊胜概率"""
    if popcount(s) <= 3:
        return 0.0                      # 狼已胜
    if endgame.lookup(w, s, WOLF) == SHEEP_WIN:
        return 1.0                      # 狼被围死(羊胜)
    if depth <= 0:
        return 0.0                      # 未见分晓,和棋=羊输
    dist = wolf_distribution(w, s)
    if not dist:
        return 1.0                      # 狼无走法=羊胜
    p = 0.0
    for (frm, to, cap), prob in dist:
        w2, s2 = apply_wolf_move(w, s, frm, to)
        if popcount(s2) <= 3:
            continue                    # 狼胜,贡献0
        v = endgame.lookup(w2, s2, SHEEP)
        if v == SHEEP_WIN:
            p += prob                   # 狼走错,羊胜
        elif v == DRAW:
            p += prob * eval_sheep_move(w2, s2, depth - 1)
        # v == WOLF_WIN: 狼胜,贡献0
    return p


def main():
    # 开局研究:狼首着 C5→C3 吃之后,轮到羊
    w1, s1 = apply_wolf_move(INIT_WOLVES, INIT_SHEEP, 2, 12)
    print(f"局面:狼首着 C5→C3 吃后,羊走(局面值="
          f"{endgame.lookup(w1, s1, SHEEP)})\n")
    cands = []
    for frm, to in sheep_moves(w1, s1):
        w2, s2 = apply_sheep_move(w1, s1, frm, to)
        if endgame.lookup(w2, s2, WOLF) != DRAW:
            continue
        p = _eval_wolf_turn(w2, s2, 3)
        cands.append((p, frm, to))
    cands.sort(reverse=True)
    print("羊方各和棋候选按'强手模型期望胜率'排序:")
    for i, (p, frm, to) in enumerate(cands[:8], 1):
        print(f"  {i}. 羊 {pos_name(frm)}→{pos_name(to)}  "
              f"P(羊胜)={p:.4f}")
    mv, info = eng.best_move(w1, s1, SHEEP, ply_budget=150)
    print(f"\n当前引擎实际会走: 羊 {pos_name(mv[0])}→{pos_name(mv[1])}")
    print("注:概率都是对'高手模型'的估计,模型参数(P_BEST/显眼度)需用真人"
          "对局数据校准;最终以你高手朋友实测为准。")


if __name__ == "__main__":
    main()

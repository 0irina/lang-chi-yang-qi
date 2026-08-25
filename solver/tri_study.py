# -*- coding: utf-8 -*-
"""三角阵(B2·C3·D1)专杀研究:
三只狼固定在该阵位,穷举羊的各种分布(k=5..10),统计狼胜/和棋/羊胜,
并找出: 1) 羊可胜的破绽局面; 2) 狼只剩唯一安全应手的"毒点"局面。
"""
import itertools
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules import WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, wolf_moves, \
    apply_wolf_move, pos_name, popcount
import endgame
from index import rank_wolf_mask, FREECELLS
from engine import Engine

eng = Engine()

# 三角阵: B2=col1,row2(下起) -> row_idx3,col1 -> 16; C3=col2,row3 -> 12; D1=col3,row1 -> 23
TRI_W = (1 << 16) | (1 << 12) | (1 << 23)
TRI_WR = int(rank_wolf_mask(TRI_W))
FREE = [int(x) for x in FREECELLS[TRI_WR]]  # 该狼形下的 22 个空位(升序,纯int)


def board_str(w, s):
    rows = []
    for r in range(5):
        line = []
        for c in range(5):
            p = r * 5 + c
            if (w >> p) & 1:
                line.append("狼")
            elif (s >> p) & 1:
                line.append("羊")
            else:
                line.append("·")
        rows.append(" ".join(line))
    return "\n".join(rows)


def wolf_safe_count(w, s):
    n = 0
    for frm, to, cap in wolf_moves(w, s):
        w2, s2 = apply_wolf_move(w, s, frm, to)
        if popcount(s2) <= 3 or endgame.lookup(w2, s2, SHEEP) != SHEEP_WIN:
            n += 1
    return n


def main():
    t0 = time.time()
    out = []
    total = {"win": 0, "draw": 0, "lose": 0}
    poison_examples = []
    lose_examples = []
    for k in range(5, 11):
        cw = cd = cl = 0
        for combo in itertools.combinations(FREE, k):
            s = 0
            for p in combo:
                s |= 1 << p
            v = endgame.lookup(TRI_W, s, WOLF)
            if v == WOLF_WIN:
                cw += 1
            elif v == SHEEP_WIN:
                cl += 1
                if len(lose_examples) < 3:
                    lose_examples.append((k, s))
            else:
                cd += 1
                if len(poison_examples) < 4:
                    n = wolf_safe_count(TRI_W, s)
                    if n == 1:
                        poison_examples.append((k, s))
        total["win"] += cw
        total["draw"] += cd
        total["lose"] += cl
        print(f"k={k}: 狼胜={cw:,} 和棋={cd:,} 羊胜={cl:,}")
        out.append(f"k={k}: 狼胜={cw:,} 和棋={cd:,} 羊胜={cl:,}")
    print(f"总计: 狼胜={total['win']:,} 和棋={total['draw']:,} "
          f"羊胜={total['lose']:,}  用时={time.time()-t0:.0f}s")

    # 羊胜破绽局面示例(含羊的取胜线)
    print("\n=== 三角阵破绽(羊可胜)示例 ===")
    for k, s in lose_examples:
        print(f"--- k={k} 羊可胜:")
        print(board_str(TRI_W, s))
        mv, info = eng.best_move(TRI_W, s, WOLF, ply_budget=150)
        print(f"狼最佳拖延: {pos_name(mv[0])}→{pos_name(mv[1])}")
        sm, si = eng.best_move(TRI_W, s, SHEEP, ply_budget=150)
        print(f"羊方致胜思路(轮到羊时): {pos_name(sm[0])}→{pos_name(sm[1])} "
              f"距终局{si['dist']}")

    # 毒点示例(狼唯一安全应手)
    print("\n=== 毒点(狼只剩唯一安全应手)示例 ===")
    for k, s in poison_examples:
        print(f"--- k={k} 毒点:")
        print(board_str(TRI_W, s))
        # 找出该唯一安全应手与所有败招数
        bad = 0
        safe_mv = None
        for frm, to, cap in wolf_moves(TRI_W, s):
            w2, s2 = apply_wolf_move(TRI_W, s, frm, to)
            if popcount(s2) <= 3 or endgame.lookup(w2, s2, SHEEP) != SHEEP_WIN:
                safe_mv = (frm, to)
            else:
                bad += 1
        print(f"唯一安全应手: {pos_name(safe_mv[0])}→{pos_name(safe_mv[1])} "
              f"| 其余 {bad} 手皆输")
        sm, si = eng.best_move(TRI_W, s, SHEEP, ply_budget=150)
        print(f"羊方推荐(轮羊走时): {pos_name(sm[0])}→{pos_name(sm[1])}")

    with open(r"D:\狼吃羊棋\三角阵研究.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("\n统计已存 D:\\狼吃羊棋\\三角阵研究.txt")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""终局引擎验收(在 dist_pass 完成、dist_check 通过后运行)。

测试:
  1. 初始局面 = 和棋;狼 8 种首着中仅 (1,3)->(3,3) 吃中羊不输,引擎首选该着。
  2. k=4 狼回合有吃子(吃后羊剩3只=新规则狼胜):引擎立即吃,值=狼胜 距离=1。
  3. 限步规则(150步和棋=狼胜)只是终局条件,绝不参与选招:
     狼胜超预算仍走最快杀棋;羊胜超预算仍走最快赢棋线(不摆烂);
     限内杀不完的羊胜线,界面按限步规则注明"到限判狼胜"。
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules import WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, wolf_moves, \
    apply_wolf_move, popcount, INIT_WOLVES, INIT_SHEEP
import endgame
import engine as eng_mod


def cell(r, c):
    return r * 5 + c


INIT_W = INIT_WOLVES  # 狼在第1行(0基第0行)2-4列: 格子1,2,3
INIT_S = INIT_SHEEP  # 羊在第3-5行: 格子10-24

fail = 0


def check(name, cond, detail=""):
    global fail
    status = "OK " if cond else "FAIL"
    if not cond:
        fail += 1
    print(f"[{status}] {name} {detail}")


def main():
    eng = eng_mod.Engine()

    # ---- 1) 初始局面(旧规则=和棋且唯一不败首着=中心吃;新规则重算后可能=狼胜) ----
    v0 = endgame.lookup(INIT_W, INIT_S, WOLF)
    if v0 == DRAW:
        check("initial value == DRAW", True, f"(got {v0})")
        move, info = eng.best_move(INIT_W, INIT_S, WOLF, ply_budget=150)
        check("initial best move = (1,3)->(3,3) capture",
              move == (cell(0, 2), cell(2, 2), True), f"(got {move})")
        nonlose = 0
        for frm, to, cap in wolf_moves(INIT_W, INIT_S):
            w2, s2 = apply_wolf_move(INIT_W, INIT_S, frm, to)
            if endgame.lookup(w2, s2, SHEEP) != SHEEP_WIN:
                nonlose += 1
        check("exactly 1 non-losing first move", nonlose == 1,
              f"(got {nonlose})")
    elif v0 == WOLF_WIN:
        check("initial value == WOLF_WIN(新规则)", True, f"(got {v0})")
        move, info = eng.best_move(INIT_W, INIT_S, WOLF, ply_budget=150)
        check("initial best move is a winning move",
              move is not None and info["value"] == WOLF_WIN, f"(got {move})")
    else:
        check("initial value in (DRAW, WOLF_WIN)", False, f"(got {v0})")

    # ---- 2) k=4 立即吃杀(吃后羊剩3只=狼胜) ----
    W2 = INIT_W
    S2 = ((1 << cell(2, 0)) | (1 << cell(2, 1))
          | (1 << cell(2, 2)) | (1 << cell(2, 3)))
    # 羊在(3,1)(3,2)(3,3)(3,4)共4只:狼 C5->C3 跳吃后剩3只即胜
    v2 = endgame.lookup(W2, S2, WOLF)
    check("k=4 position is wolf-win (capture to 3)", v2 == WOLF_WIN,
          f"(got {v2})")
    move2, info2 = eng.best_move(W2, S2, WOLF, ply_budget=100)
    check("k=4: engine captures immediately", move2[2] is True,
          f"(got {move2})")
    check("k=4: value=WOLF_WIN dist=0(吃后即终局)",
          info2["value"] == WOLF_WIN and info2["dist"] == 0,
          f"(v={info2['value']} d={info2['dist']})")

    # ---- 3) 150 步规则(随机找 5 个 d>=3 的狼胜局面) ----
    rng = random.Random(20260822)
    found = 0
    trials = 0
    while found < 5 and trials < 500000:
        trials += 1
        k = rng.choice([4, 5, 6])
        cells = rng.sample(range(25), 3 + k)
        w = 0
        for c in cells[:3]:
            w |= 1 << c
        s = 0
        for c in cells[3:]:
            s |= 1 << c
        if endgame.lookup(w, s, WOLF) != WOLF_WIN:
            continue
        d = endgame.lookup_dist(w, s, WOLF)
        if d < 3 or d > 300:
            continue
        m1, i1 = eng.best_move(w, s, WOLF, ply_budget=d - 1)
        m2, i2 = eng.best_move(w, s, WOLF, ply_budget=d - 2)
        check(f"case{found}: d={d} budget=d-1 -> WOLF_WIN",
              i1["value"] == WOLF_WIN, f"(got {i1['value']})")
        check(f"case{found}: d={d} budget=d-2 -> 仍WOLF_WIN(到限判狼胜)",
              i2["value"] == WOLF_WIN, f"(got {i2['value']})")
        found += 1
    if found < 5:
        check("found 5 wolf-win samples with d>=3", False, f"(got {found})")

    # ---- 4) 限步规则(羊侧):羊胜所需步数超预算,羊仍走最快赢棋线(不摆烂) ----
    found = 0
    trials = 0
    while found < 3 and trials < 500000:
        trials += 1
        k = rng.choice([4, 5, 6])
        cells = rng.sample(range(25), 3 + k)
        w = 0
        for c in cells[:3]:
            w |= 1 << c
        s = 0
        for c in cells[3:]:
            s |= 1 << c
        if endgame.lookup(w, s, SHEEP) != SHEEP_WIN:
            continue
        d = endgame.lookup_dist(w, s, SHEEP)
        if d < 3 or d > 300:
            continue
        m1, i1 = eng.best_move(w, s, SHEEP, ply_budget=d - 1)
        m2, i2 = eng.best_move(w, s, SHEEP, ply_budget=d - 2)
        check(f"sheep{found}: d={d} budget=d-1 -> 最快羊胜线",
              i1["value"] == SHEEP_WIN and i1["dist"] == d - 1,
              f"(v={i1['value']} d={i1['dist']})")
        check(f"sheep{found}: d={d} budget=d-2 -> 限内杀不完仍走最快线(不摆烂)",
              i2["value"] == SHEEP_WIN and i2["dist"] == d - 1,
              f"(v={i2['value']} d={i2['dist']})")
        found += 1
    if found < 3:
        check("found 3 sheep-win samples with d>=3", False, f"(got {found})")

    print("RESULT:", "ALL OK" if fail == 0 else f"{fail} FAILURES")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""规则、索引、残局表的单元测试。

用法:python solver/tests.py [max_k]   (默认 5)
"""
import random
import sys

import rules
from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW,
                   INIT_WOLVES, INIT_SHEEP, popcount,
                   wolf_moves, sheep_moves, apply_wolf_move, outcome)
import index
import endgame


def test_start_moves():
    wm = wolf_moves(INIT_WOLVES, INIT_SHEEP)
    sm = sheep_moves(INIT_WOLVES, INIT_SHEEP)
    assert len(wm) == 8, f"狼初始走法应为 8,实际 {len(wm)}"
    assert len(sm) == 5, f"羊初始走法应为 5,实际 {len(sm)}"


def test_capture_terminal():
    W = (1 << 1) | (1 << 2) | (1 << 3)
    S = (1 << 11) | (1 << 20) | (1 << 24)  # (2,1),(4,0),(4,4)
    caps = [m for m in wolf_moves(W, S) if m[2]]
    assert (1, 11, True) in caps, "应存在 (0,1)->(2,1) 的吃子"
    # 新规则:羊剩3只即终局狼胜(任何回合、任何走法之前)
    term, win = outcome(W, S, WOLF)
    assert term and win == WOLF_WIN
    W2, S2 = apply_wolf_move(W, S, 1, 11)
    assert popcount(S2) == 2
    term2, win2 = outcome(W2, S2, SHEEP)
    assert term2 and win2 == WOLF_WIN


def test_wolf_boxed():
    W = (1 << 0) | (1 << 1) | (1 << 5)
    S = (1 << 2) | (1 << 6) | (1 << 10) | (1 << 11)  # 4只羊围死狼(新规则下k=4)
    assert wolf_moves(W, S) == []
    term, win = outcome(W, S, WOLF)
    assert term and win == SHEEP_WIN


def test_sheep_stuck():
    W = (1 << 22) | (1 << 16) | (1 << 10)  # (4,2),(3,1),(2,0)
    S = (1 << 20) | (1 << 21) | (1 << 15)  # (4,0),(4,1),(3,0)
    assert sheep_moves(W, S) == []
    term, win = outcome(W, S, SHEEP)
    assert term and win == WOLF_WIN  # 羊无路可走=狼胜(该局面羊仅3只,本就终局)


def test_index_roundtrip():
    # 狼:全部 2300 个摆法往返
    for wr in range(2300):
        m = index.unrank_wolf_mask(wr)
        assert index.rank_wolf_mask(m) == wr
        assert m.bit_count() == 3
    # 羊:随机摆法往返
    rng = random.Random(42)
    for _ in range(300):
        cells = rng.sample(range(25), 3)
        W = sum(1 << p for p in cells)
        wr = index.rank_wolf_mask(W)
        k = rng.randint(3, 15)
        free = [p for p in range(25) if not ((W >> p) & 1)]
        sheep_cells = rng.sample(free, k)
        S = sum(1 << p for p in sheep_cells)
        sr = index.rank_sheep_mask(wr, S)
        assert index.unrank_sheep_mask(wr, sr, k) == S, (wr, k, sr)


def test_endgame_hands():
    endgame.load_tables()
    # 羊剩 3 只(新规则:双方回合均狼胜)
    W = (1 << 1) | (1 << 2) | (1 << 3)
    S = (1 << 11) | (1 << 20) | (1 << 24)
    assert endgame.lookup(W, S, WOLF) == WOLF_WIN
    # 狼被围死(4羊,k=4) → 羊胜
    W2 = (1 << 0) | (1 << 1) | (1 << 5)
    S2 = (1 << 2) | (1 << 6) | (1 << 10) | (1 << 11)
    assert endgame.lookup(W2, S2, WOLF) == SHEEP_WIN
    # 羊被堵死(羊回合)→ 狼胜
    W3 = (1 << 22) | (1 << 16) | (1 << 10)
    S3 = (1 << 20) | (1 << 21) | (1 << 15)
    assert endgame.lookup(W3, S3, SHEEP) == WOLF_WIN
    # 初始局面羊数=15:全表下为和棋(新规则重算后可能变为狼胜),绝不该是羊胜/未解
    v_init = endgame.lookup(INIT_WOLVES, INIT_SHEEP, WOLF)
    assert v_init in (DRAW, WOLF_WIN), f"(got {v_init})"


def main():
    max_k = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    print("== 规则测试 ==")
    test_start_moves()
    print("  初始走法数: 狼 8 / 羊 5  OK")
    test_capture_terminal()
    print("  跳2吃羊/剩3羊狼胜  OK")
    test_wolf_boxed()
    print("  狼被围死羊胜  OK")
    test_sheep_stuck()
    print("  羊被堵死狼胜  OK")
    print("== 索引测试 ==")
    test_index_roundtrip()
    print("  编解码往返  OK")
    print(f"== 构建残局表 k=3..{max_k} ==")
    endgame.build(max_k)
    print("== 残局表手工验证 ==")
    test_endgame_hands()
    print("  手工局面全部正确  OK")
    print("\nALL TESTS PASSED")


if __name__ == "__main__":
    main()

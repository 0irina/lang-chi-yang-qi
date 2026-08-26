# -*- coding: utf-8 -*-
"""高压走廊开局书测试:
1) 书内所有走法:合法、走后仍和棋、且走后狼恰有唯一不败着法+至少1条败着;
2) AI羊在书内局面只走书内走法(轮换开/关两种);
3) 沿走廊(狼走唯一正招)连走12回合,全程和棋;
4) 狼在书内局面走任何非唯一正招 -> 直接羊胜("走错就输")。
"""
import os
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import endgame
from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW,
                   pos_name, wolf_moves, sheep_moves,
                   apply_wolf_move, apply_sheep_move, popcount,
                   INIT_WOLVES, INIT_SHEEP)
import opening_book
import opening_book2
from engine import Engine


def wolf_unique_draw(w, s):
    """狼走局面:返回 (唯一不败(和)着法列表, 败着列表)。"""
    dm = []
    lose = []
    for a, b, cap in wolf_moves(w, s):
        w2, s2 = apply_wolf_move(w, s, a, b)
        if popcount(s2) <= 3:
            dm.append((a, b, cap))
            continue
        v = endgame.lookup(w2, s2, SHEEP)
        if v == DRAW:
            dm.append((a, b, cap))
        elif v == SHEEP_WIN:
            lose.append((a, b, cap))
    return dm, lose


def main():
    endgame.load_tables()
    # 1) 书条目性质
    n = 0
    for (w, s), moves in opening_book.BOOK.items():
        assert moves, "空走法列表"
        for a, b in moves:
            assert any((x, y) == (a, b) for x, y in sheep_moves(w, s)), \
                f"非法走法 {pos_name(a)}→{pos_name(b)}"
            w2, s2 = apply_sheep_move(w, s, a, b)
            assert endgame.lookup(w2, s2, WOLF) == DRAW, \
                f"走后非和棋 {pos_name(a)}→{pos_name(b)}"
            dm, lose = wolf_unique_draw(w2, s2)
            assert len(dm) == 1, \
                f"狼和着数={len(dm)} != 1 @ {pos_name(a)}→{pos_name(b)}"
            assert lose, f"狼无败着(无压力) @ {pos_name(a)}→{pos_name(b)}"
        n += 1
    print(f"书条目性质: {n} 个局面全部 OK(合法/和棋/狼唯一正招/有败着)")

    # 2) AI羊书内选招(轮换开关两种);先走狼唯一首着 C5→C3
    for variety in (False, True):
        eng = Engine()
        eng.opening_variety = variety
        eng.rng = random.Random(7)
        w, s = apply_wolf_move(INIT_WOLVES, INIT_SHEEP, 2, 12)
        hist = [INIT_WOLVES, INIT_SHEEP, (w, s)]
        for _ in range(12):
            mv, info = eng.best_move(w, s, SHEEP, history=hist)
            assert (mv[0], mv[1]) in opening_book.BOOK[(w, s)], \
                f"AI羊未走书内走法: {pos_name(mv[0])}→{pos_name(mv[1])}"
            w, s = apply_sheep_move(w, s, mv[0], mv[1])
            hist.append((w, s))
            dm, lose = wolf_unique_draw(w, s)
            assert len(dm) == 1
            wa, wb, wcap = dm[0]
            w, s = apply_wolf_move(w, s, wa, wb)
            hist.append((w, s))
        print(f"AI羊书内选招(variety={variety}): 12回合全走书内走法 OK")

    # 3) 狼走错即输:走廊局面中,狼任一败着 -> 羊胜
    eng = Engine()
    eng.opening_variety = True
    eng.rng = random.Random(11)
    w, s = apply_wolf_move(INIT_WOLVES, INIT_SHEEP, 2, 12)
    hist = [INIT_WOLVES, INIT_SHEEP, (w, s)]
    for _ in range(3):
        mv, info = eng.best_move(w, s, SHEEP, history=hist)
        w, s = apply_sheep_move(w, s, mv[0], mv[1])
        hist.append((w, s))
        dm, lose = wolf_unique_draw(w, s)
        wa, wb, wcap = dm[0]
        w, s = apply_wolf_move(w, s, wa, wb)
        hist.append((w, s))
    mv, info = eng.best_move(w, s, SHEEP, history=hist)
    w, s = apply_sheep_move(w, s, mv[0], mv[1])
    dm, lose = wolf_unique_draw(w, s)
    assert len(dm) == 1 and lose
    for wa, wb, wcap in lose:
        w2, s2 = apply_wolf_move(w, s, wa, wb)
        v = (WOLF_WIN if popcount(s2) <= 3
             else endgame.lookup(w2, s2, SHEEP))
        assert v == SHEEP_WIN, \
            f"狼败着 {pos_name(wa)}→{pos_name(wb)} 走后非羊胜: {v}"
    print(f"走错即输: 狼 {len(lose)} 条败着全部 -> 羊胜 OK")

    # 5) 次选高压书(BOOK2):条目性质 + 不与主选走法重叠 + 引擎在次选局面选次选走法
    n2 = 0
    for (w, s), moves in opening_book2.BOOK2.items():
        for a, b in moves:
            assert any((x, y) == (a, b) for x, y in sheep_moves(w, s)), \
                f"次选非法走法 {pos_name(a)}→{pos_name(b)}"
            w2, s2 = apply_sheep_move(w, s, a, b)
            assert endgame.lookup(w2, s2, WOLF) == DRAW
            dm, lose = wolf_unique_draw(w2, s2)
            assert 1 <= len(dm) <= 2, f"狼正招数={len(dm)} 超出次选范围"
            pbm = opening_book.BOOK.get((w, s))
            assert not (pbm and (a, b) in pbm), "次选与主选走法重叠"
        n2 += 1
    print(f"次选书条目性质: {n2} 个局面全部 OK(合法/和棋/狼正招<=2/不与主选走法重叠)")

    cand2 = [(w, s) for (w, s) in opening_book2.BOOK2
             if (w, s) not in opening_book.BOOK
             and endgame.lookup(w, s, SHEEP) == DRAW]
    assert cand2, "次选书应有仅次选的和棋局面"
    eng3 = Engine()
    eng3.opening_variety = False
    w, s = cand2[0]
    mv, info = eng3.best_move(w, s, SHEEP, history=())
    assert (mv[0], mv[1]) in opening_book2.BOOK2[(w, s)], \
        f"引擎未选次选走法: {pos_name(mv[0])}→{pos_name(mv[1])}"
    print("引擎次选局面选次选走法 OK")

    # 6) 镜像对称:每个书条目(主选/次选)的镜像局面存在且镜像走法齐全
    def _mpos(p):
        return (p // 5) * 5 + (4 - p % 5)

    def _mstate(w, s):
        mw = ms = 0
        x = w
        while x:
            lsb = x & -x
            mw |= 1 << _mpos(lsb.bit_length() - 1)
            x ^= lsb
        x = s
        while x:
            lsb = x & -x
            ms |= 1 << _mpos(lsb.bit_length() - 1)
            x ^= lsb
        return mw, ms

    for book, name in ((opening_book.BOOK, "主选"),
                       (opening_book2.BOOK2, "次选")):
        for (w, s), moves in book.items():
            mw, mss = _mstate(w, s)
            assert (mw, mss) in book, f"{name}书缺镜像局面"
            tgt = book[(mw, mss)]
            for a, b in moves:
                assert (_mpos(a), _mpos(b)) in tgt, \
                    f"{name}书缺镜像走法 {pos_name(a)}→{pos_name(b)}"
    print("镜像对称检查: 主选/次选书全部 OK")
    print("RESULT: ALL OK")


if __name__ == "__main__":
    main()

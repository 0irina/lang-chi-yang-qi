# -*- coding: utf-8 -*-
"""堡垒博弈(严谨版):从开局出发,完整博弈树(羊必须变招,狼可重复):
  狼 = 穷尽一切吃法求"羊最少";
  羊 = 穷尽一切变招求"羊最多";
  羊一旦进入"堡垒"(狼回合,当前无安全吃子且8层深搜内狼吃不到)即保住全部羊。
全部走法穷举 + alpha-beta + 置换表 + 迭代加深。返回羊能保住的羊数。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, popcount,
                   wolf_moves, sheep_moves, apply_wolf_move, apply_sheep_move,
                   INIT_WOLVES, INIT_SHEEP)
import endgame

endgame.load_tables()

NODES = 0
TT = {}


def no_safe_caps(w, s):
    for frm, to, cap in wolf_moves(w, s):
        if not cap:
            continue
        w2, s2 = apply_wolf_move(w, s, frm, to)
        if popcount(s2) <= 3 or endgame.lookup(w2, s2, SHEEP) != SHEEP_WIN:
            return False
    return True


def fortress_holds(w, s, turn, seen, depth):
    if popcount(s) <= 3:
        return False
    if depth <= 0:
        return True
    key = (w, s, turn)
    if key in seen:
        return True
    seen = seen | {key}
    if turn == WOLF:
        for frm, to, cap in wolf_moves(w, s):
            w2, s2 = apply_wolf_move(w, s, frm, to)
            if cap:
                # 任一安全吃子(吃后非羊胜)= 堡垒被攻破
                if popcount(s2) <= 3 or \
                        endgame.lookup(w2, s2, SHEEP) != SHEEP_WIN:
                    return False
                continue
            if endgame.lookup(w2, s2, SHEEP) == SHEEP_WIN:
                continue
            if not fortress_holds(w2, s2, SHEEP, seen, depth - 1):
                return False
        return True
    else:
        for frm, to in sheep_moves(w, s):
            w2, s2 = apply_sheep_move(w, s, frm, to)
            if (w2, s2, WOLF) in seen:
                continue
            if fortress_holds(w2, s2, WOLF, seen, depth - 1):
                return True
        return False


def fortress_ok(w, s):
    """堡垒判定(仅狼回合调用):当前无安全吃子 + 8层深搜内狼吃不到"""
    if not no_safe_caps(w, s):
        return False
    return fortress_holds(w, s, WOLF, frozenset(), 8)


def wolf_moves_sorted(w, s):
    ms = wolf_moves(w, s)
    def key(m):
        w2, s2 = apply_wolf_move(w, s, m[0], m[1])
        return (0 if m[2] else 1, popcount(s2))
    ms.sort(key=key)
    return ms


def sheep_moves_sorted(w, s):
    ms = sheep_moves(w, s)
    def key(m):
        w2, s2 = apply_sheep_move(w, s, m[0], m[1])
        if fortress_ok(w2, s2):
            return (0, 0)
        safe = 0
        for f2, t2, c2 in wolf_moves(w2, s2):
            if not c2:
                continue
            w3, s3 = apply_wolf_move(w2, s2, f2, t2)
            if popcount(s3) <= 3 or \
                    endgame.lookup(w3, s3, SHEEP) != SHEEP_WIN:
                safe += 1
        return (1, safe)
    ms.sort(key=key)
    return ms


def search(w, s, turn, hist, depth, alpha, beta):
    global NODES
    NODES += 1
    k = popcount(s)
    if k <= 3:
        return 0
    if turn == WOLF and fortress_ok(w, s):
        return k                      # 羊已保住 k 只
    if depth <= 0:
        return 0
    key = (w, s, turn)
    r = TT.get(key)
    if r is not None:
        return r[0]
    hist = hist | {(w, s)}
    if turn == WOLF:
        best = 99
        bmv = None
        for m in wolf_moves_sorted(w, s):
            w2, s2 = apply_wolf_move(w, s, m[0], m[1])
            if endgame.lookup(w2, s2, SHEEP) == SHEEP_WIN:
                continue                # 狼不走败招
            v = search(w2, s2, SHEEP, hist, depth - 1, alpha, beta)
            if v < best:
                best = v
                bmv = m
                if best < beta:
                    beta = best
            if alpha >= beta:
                break
    else:
        best = 0
        bmv = None
        for m in sheep_moves_sorted(w, s):
            w2, s2 = apply_sheep_move(w, s, m[0], m[1])
            if (w2, s2) in hist:
                continue                # 羊必须变招,不走重复
            v = search(w2, s2, WOLF, hist, depth - 1, alpha, beta)
            if v > best:
                best = v
                bmv = m
                if best > alpha:
                    alpha = best
            if alpha >= beta:
                break
    TT[key] = (best, bmv)
    return best


if __name__ == "__main__":
    t0 = time.time()
    ans = None
    for d in (8, 12, 16, 20):
        TT.clear()
        NODES = 0
        t1 = time.time()
        ans = search(INIT_WOLVES, INIT_SHEEP, WOLF, frozenset(), d, 0, 16)
        print(f"深度{d}: 羊可保住 = {ans}  节点={NODES:,}  "
              f"用时={time.time()-t1:.1f}s", flush=True)
        if time.time() - t0 > 3300:
            print("接近1小时预算,停止加深", flush=True)
            break
    # 沿置换表重建主变线
    print(f"\n最终答案: 从开局出发(双方穷尽最优+羊必须变招),羊最多可剩 = {ans}")
    print("\n主变线(狼穷尽吃法 / 羊最优保羊):")
    w, s, t = INIT_WOLVES, INIT_SHEEP, WOLF
    hist = {(w, s)}
    k0 = popcount(s)
    steps = 0
    while steps < 40:
        key = (w, s, t)
        r = TT.get(key)
        if r is None or r[1] is None:
            break
        m = r[1]
        cap = t == WOLF and (popcount(s) -
                             popcount(apply_wolf_move(w, s, m[0], m[1])[1])) > 0
        print(f"  {'狼' if t == WOLF else '羊'} {pos_name(m[0])}→{pos_name(m[1])}"
              f"{' 吃' if cap else ''}"
              f"   (羊剩 {popcount(apply_wolf_move(w, s, m[0], m[1])[1] if t == WOLF else s)})")
        if t == WOLF:
            w, s = apply_wolf_move(w, s, m[0], m[1])
        else:
            w, s = apply_sheep_move(w, s, m[0], m[1])
        if popcount(s) <= 3:
            print("  (狼吃剩3只——说明羊没能保住,与答案不符!)")
            break
        t = 1 - t
        steps += 1


# -*- coding: utf-8 -*-
"""深度优先探针:宽松压力下(狼每步正招<=MAX_WC)能撑多深?
DFS 沿"压力着法"深挖(路径内去重防循环),报告最深线路与深度分布。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import endgame
from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW,
                   pos_name, wolf_moves, sheep_moves,
                   apply_wolf_move, apply_sheep_move, popcount,
                   INIT_WOLVES, INIT_SHEEP)

MAX_WC = int(sys.argv[1]) if len(sys.argv) > 1 else 2
NODE_BUDGET = int(sys.argv[2]) if len(sys.argv) > 2 else 400_000

_lc = {}
_wc_cache = {}


def L(w, s, turn):
    key = (w, s, turn)
    v = _lc.get(key)
    if v is None:
        v = endgame.lookup(w, s, turn)
        if len(_lc) > 6_000_000:
            _lc.clear()
        _lc[key] = v
    return v


def wolf_stats(w, s):
    got = _wc_cache.get((w, s))
    if got is not None:
        return got
    dm = []
    for a, b, cap in wolf_moves(w, s):
        w2, s2 = apply_wolf_move(w, s, a, b)
        if popcount(s2) <= 3:
            continue
        if L(w2, s2, SHEEP) == DRAW:
            dm.append((a, b, cap))
    if len(_wc_cache) > 4_000_000:
        _wc_cache.clear()
    _wc_cache[(w, s)] = dm
    return dm


def pressure_moves(w, s):
    """羊走局面 -> [(羊走法, 狼正招列表, 狼正招数)] 按正招数升序。"""
    out = []
    for a, b in sheep_moves(w, s):
        w2, s2 = apply_sheep_move(w, s, a, b)
        if L(w2, s2, WOLF) != DRAW:
            continue
        dm = wolf_stats(w2, s2)
        if 1 <= len(dm) <= MAX_WC:
            out.append(((a, b), dm))
    out.sort(key=lambda x: len(x[1]))
    return out


def main():
    t0 = time.time()
    endgame.load_tables()
    w, s = apply_wolf_move(INIT_WOLVES, INIT_SHEEP, 2, 12)

    best = []            # 最深线路 (羊招, 狼招, wc) 列表
    best_ply = 1
    nodes = 0
    depth_hist = {}
    over22 = 0
    path = []            # (w,s) 路径状态
    path_set = {(w, s)}

    def dfs(w, s, ply, moves):
        nonlocal nodes, best, best_ply, over22
        nodes += 1
        if nodes > NODE_BUDGET:
            return
        if ply > best_ply:
            best_ply = ply
            best = list(moves)
        if ply >= 45:
            over22 += 1
        if ply >= 120:
            return
        for (a, b), dm in pressure_moves(w, s):
            w2, s2 = apply_sheep_move(w, s, a, b)
            for wa, wb_, wcap in dm:
                w3, s3 = apply_wolf_move(w2, s2, wa, wb_)
                if (w3, s3) in path_set:
                    continue
                path_set.add((w3, s3))
                dfs(w3, s3, ply + 2,
                    moves + [((a, b), (wa, wb_, wcap), len(dm))])
                path_set.discard((w3, s3))
                if nodes > NODE_BUDGET:
                    return

    dfs(w, s, 1, [])
    print(f"DFS探针 MAX_WC={MAX_WC} 预算{NODE_BUDGET} 用时 {time.time()-t0:.0f}s")
    print(f"最深高压线: {best_ply - 1} 手(狼高压 {(best_ply - 1) // 2} 回合)")
    print(f"深度>=45手(超过严格版22回合)的分支数: {over22}")
    seq = ["狼C5→C3吃"]
    for (a, b), (wa, wb_, wcap), wc in best:
        seq.append(f"羊{pos_name(a)}→{pos_name(b)}")
        seq.append(f"狼{pos_name(wa)}→{pos_name(wb_)}"
                   f"{'吃' if wcap else ''}(正招{wc})")
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "dfs_probe_report.txt"), "w", encoding="utf-8") as f:
        f.write(f"MAX_WC={MAX_WC} 最深 {best_ply - 1} 手\n")
        f.write(" ".join(seq) + "\n")
    print("线路已写入 dfs_probe_report.txt")


if __name__ == "__main__":
    main()

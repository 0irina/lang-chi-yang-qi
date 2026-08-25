# -*- coding: utf-8 -*-
"""宽松高压走廊搜索:允许狼每步最多 MAX_WC 条正招(默认2),找出能持续
更久的高压线。狼的正招会分叉(狼有选择),因此线路是一棵树:
  羊走局面 -> [保持压力的羊走法],每条羊走法 -> 狼各条正招 -> 新羊走局面
输出:
  relaxed_corridor_report.txt  深度/状态数/正招数分布/最深线路
  relaxed_corridor_book.json   压力安全书(羊走局面 -> 走法列表)
"""
import os
import sys
import json
import time
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import endgame
from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW,
                   pos_name, wolf_moves, sheep_moves,
                   apply_wolf_move, apply_sheep_move, popcount,
                   INIT_WOLVES, INIT_SHEEP)

MAX_WC = int(sys.argv[1]) if len(sys.argv) > 1 else 2
MAX_NODES = 1_500_000
HERE = os.path.dirname(os.path.abspath(__file__))

_lc = {}
_wolf_cache = {}


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
    got = _wolf_cache.get((w, s))
    if got is not None:
        return got
    dm = []
    nl = 0
    nt = 0
    for a, b, cap in wolf_moves(w, s):
        w2, s2 = apply_wolf_move(w, s, a, b)
        nt += 1
        if popcount(s2) <= 3:
            continue
        v = L(w2, s2, SHEEP)
        if v == DRAW:
            dm.append((a, b, cap))
        elif v == SHEEP_WIN:
            nl += 1
    if len(_wolf_cache) > 4_000_000:
        _wolf_cache.clear()
    _wolf_cache[(w, s)] = (dm, nl, nt)
    return dm, nl, nt


def sheep_draw_moves(w, s):
    out = []
    for a, b in sheep_moves(w, s):
        w2, s2 = apply_sheep_move(w, s, a, b)
        if L(w2, s2, WOLF) == DRAW:
            out.append((a, b))
    return out


def main():
    t0 = time.time()
    endgame.load_tables()
    w, s = apply_wolf_move(INIT_WOLVES, INIT_SHEEP, 2, 12)
    # node = (w, s, parent, 羊招, 狼招, 该步狼正招数)
    nodes = [(w, s, -1, None, None, 0)]
    ply_of = [1]
    has_press = [False]      # 该羊走局面是否仍有"压力着法"
    visited = {(w, s): 0}
    q = collections.deque([0])
    max_ply = 1
    max_idx = 0
    wc_hist = collections.Counter()
    t_last = time.time()

    while q and len(nodes) < MAX_NODES:
        idx = q.popleft()
        w, s, par, smv, wmv, wc0 = nodes[idx]
        ply = ply_of[idx]
        any_press = False
        for a, b in sheep_draw_moves(w, s):
            w2, s2 = apply_sheep_move(w, s, a, b)
            dm, nl, nt = wolf_stats(w2, s2)
            if len(dm) > MAX_WC:
                continue
            any_press = True
            wc_hist[len(dm)] += 1
            for wa, wb_, wcap in dm:
                w3, s3 = apply_wolf_move(w2, s2, wa, wb_)
                if (w3, s3) in visited:
                    continue
                visited[(w3, s3)] = len(nodes)
                nodes.append((w3, s3, idx, (a, b), (wa, wb_, wcap),
                              len(dm)))
                ply_of.append(ply + 2)
                has_press.append(False)
                q.append(len(nodes) - 1)
                if ply + 2 > max_ply:
                    max_ply = ply + 2
                    max_idx = len(nodes) - 1
        has_press[idx] = any_press
        if time.time() - t_last > 30:
            t_last = time.time()
            print(f"  节点 {len(nodes):,}  最深 {max_ply} 手  "
                  f"耗时 {time.time()-t0:.0f}s", flush=True)

    print(f"搜索结束: MAX_WC={MAX_WC} 节点 {len(nodes):,} "
          f"最深 {max_ply} 手 耗时 {time.time()-t0:.0f}s")

    # 最深线路重建
    chain = []
    idx = max_idx
    while idx > 0:
        chain.append(idx)
        idx = nodes[idx][2]
    chain.reverse()
    seq = ["狼C5→C3吃"]
    wcs = []
    for c in chain:
        w, s, par, smv, wmv, wc0 = nodes[c]
        seq.append(f"羊{pos_name(smv[0])}→{pos_name(smv[1])}")
        seq.append(f"狼{pos_name(wmv[0])}→{pos_name(wmv[1])}"
                   f"{'吃' if wmv[2] else ''}(正招{wc0})")
        wcs.append(wc0)

    # 压力安全书:羊走法的所有狼正招后继都仍有压力着法
    book = {}
    n_safe = 0
    for i, (w, s, par, smv, wmv, wc0) in enumerate(nodes):
        if not has_press[i]:
            continue
        moves = []
        for a, b in sheep_draw_moves(w, s):
            w2, s2 = apply_sheep_move(w, s, a, b)
            dm, nl, nt = wolf_stats(w2, s2)
            if len(dm) > MAX_WC:
                continue
            ok = True
            for wa, wb_, wcap in dm:
                w3, s3 = apply_wolf_move(w2, s2, wa, wb_)
                j = visited.get((w3, s3))
                if j is None or not has_press[j]:
                    ok = False
                    break
            if ok:
                moves.append([a, b])
        if moves:
            book[f"{w}:{s}"] = moves
            n_safe += 1

    with open(os.path.join(HERE, "relaxed_corridor_report.txt"), "w",
              encoding="utf-8") as f:
        f.write(f"宽松高压走廊 MAX_WC={MAX_WC}:\n")
        f.write(f"  羊走局面数: {len(nodes):,}  最深高压线: {max_ply} 手"
                f"(狼高压回合 {(max_ply - 1) // 2})\n")
        f.write(f"  狼正招数分布(每步羊走后): "
                f"{dict(sorted(wc_hist.items()))}\n")
        f.write(f"  仍有压力着法的局面: "
                f"{sum(1 for h in has_press if h):,}\n")
        f.write(f"  压力安全书局面数: {n_safe}\n")
        f.write(f"  最深线路({max_ply - 1}手):\n")
        f.write("    " + " ".join(seq) + "\n")
    with open(os.path.join(HERE, "relaxed_corridor_book.json"), "w",
              encoding="utf-8") as f:
        json.dump(book, f, ensure_ascii=False, indent=1)
    print(f"报告: relaxed_corridor_report.txt")
    print(f"书:   relaxed_corridor_book.json")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""高压走廊开局搜索(BFS,全破解表):
从初始局面出发,只沿"羊走后狼恰好只有 1 个不败着法(和棋)"的线路扩展。
- 狼的"唯一正招"是被迫走的(和1),走任何别的都直接羊胜;
- 羊在每步的分支中只保留"仍能让狼和1"的走法;
- 状态去重(羊走局面)防循环;查表带缓存。
输出:
  corridor_lines.txt  —— 人读:每条最长走廊线的长度/羊裕度/狼败着数与走法序列
  corridor_book.json  —— 机读:羊走局面 -> (走法, 羊裕度, 狼败着数)
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

MAX_PLIES = 120          # 每步=1手,120手=60个羊回合
MAX_NODES = 400_000
OUT_LINES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "corridor_lines.txt")
OUT_BOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "corridor_book.json")

_lc = {}
_wolf_cache = {}


def L(w, s, turn):
    key = (w, s, turn)
    v = _lc.get(key)
    if v is None:
        v = endgame.lookup(w, s, turn)
        if len(_lc) > 4_000_000:
            _lc.clear()
        _lc[key] = v
    return v


def wolf_stats(w, s):
    """狼走局面 (w,s): 返回 (不败(和棋)走法列表, 败着数, 总着数)。"""
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
            continue  # 直接吃胜;在DRAW局面不会出现,防御性跳过
        v = L(w2, s2, SHEEP)
        if v == DRAW:
            dm.append((a, b, cap))
        elif v == SHEEP_WIN:
            nl += 1
    if len(_wolf_cache) > 3_000_000:
        _wolf_cache.clear()
    _wolf_cache[(w, s)] = (dm, nl, nt)
    return dm, nl, nt


def sheep_draw_moves(w, s):
    """羊走局面 (w,s): 返回所有走后仍和棋的羊走法。"""
    out = []
    for a, b in sheep_moves(w, s):
        w2, s2 = apply_sheep_move(w, s, a, b)
        if L(w2, s2, WOLF) == DRAW:
            out.append((a, b))
    return out


def main():
    t0 = time.time()
    endgame.load_tables()
    print("表加载: full" if endgame._FULL is not None else "表加载失败")

    # 首着:狼唯一正招 C5→C3 吃 (pos 2 -> 12)
    w, s = apply_wolf_move(INIT_WOLVES, INIT_SHEEP, 2, 12)
    nodes = [(w, s, -1, None, None, 0, 0)]   # (w,s,parent,羊招,狼招,羊裕度,狼败着)
    ply_of = [1]
    visited = {(w, s)}
    q = collections.deque([0])
    frontier = []
    t_last = time.time()

    while q and len(nodes) < MAX_NODES:
        idx = q.popleft()
        w, s, par, smv, wmv, marg, nl = nodes[idx]
        ply = ply_of[idx]
        if ply >= MAX_PLIES:
            frontier.append(idx)
            continue
        sdm = sheep_draw_moves(w, s)
        if not sdm:
            frontier.append(idx)
            continue
        # 羊裕度 = 走后仍和棋的羊着法数
        margin = len(sdm)
        extended = False
        for a, b in sdm:
            w2, s2 = apply_sheep_move(w, s, a, b)
            dm, nl2, nt = wolf_stats(w2, s2)
            if len(dm) != 1:
                continue          # 狼和着 != 1:走廊在此分支结束
            wa, wb, wcap = dm[0]
            w3, s3 = apply_wolf_move(w2, s2, wa, wb)
            if (w3, s3) in visited:
                continue
            visited.add((w3, s3))
            nodes.append((w3, s3, idx, (a, b), (wa, wb, wcap), margin, nl2))
            ply_of.append(ply + 2)
            q.append(len(nodes) - 1)
            extended = True
        if not extended:
            frontier.append(idx)
        if time.time() - t_last > 30:
            t_last = time.time()
            print(f"  节点 {len(nodes):,}  队列 {len(q):,}  "
                  f"耗时 {time.time()-t0:.0f}s", flush=True)

    print(f"搜索结束: 节点 {len(nodes):,}  走廊终点 {len(frontier):,}  "
          f"耗时 {time.time()-t0:.0f}s")

    # 重建每条终点线(按正确时间顺序: 羊2, 狼3, 羊4, 狼5 ...)
    lines = []
    for fi in frontier:
        chain = []
        idx = fi
        while idx > 0:
            chain.append(idx)
            idx = nodes[idx][2]
        chain.reverse()
        path = []
        for idx in chain:
            w, s, par, smv, wmv, marg, nl = nodes[idx]
            path.append(("羊", smv, marg))
            path.append(("狼", wmv, nl))
        lines.append(path)

    # 合法性校验: 逐线回放,断言每步合法且走后仍和棋
    bad = 0
    for path in lines:
        w, s = INIT_WOLVES, INIT_SHEEP
        ok = True
        for who, mv, _x in [("狼", (2, 12, True), 0)] + path:
            if who == "狼":
                if not any((a, b) == (mv[0], mv[1])
                           for a, b, cap in wolf_moves(w, s)):
                    ok = False
                    break
                w, s = apply_wolf_move(w, s, mv[0], mv[1])
                if popcount(s) <= 3:
                    continue
                if L(w, s, SHEEP) != DRAW:
                    ok = False
                    break
            else:
                if not any((a, b) == (mv[0], mv[1])
                           for a, b in sheep_moves(w, s)):
                    ok = False
                    break
                w, s = apply_sheep_move(w, s, mv[0], mv[1])
                if L(w, s, WOLF) != DRAW:
                    ok = False
                    break
        if not ok:
            bad += 1
    print(f"线路合法性校验: {len(lines) - bad}/{len(lines)} 条全部合法")
    if bad:
        print(f"!! {bad} 条非法")

    def line_info(path):
        corr = len([1 for p in path if p[0] == "狼"])
        mins = min(p[2] for p in path if p[0] == "羊")
        avgnl = (sum(p[2] for p in path if p[0] == "狼")
                 / max(1, corr))
        return corr, mins, avgnl

    lines.sort(key=line_info, reverse=True)

    book = {}
    with open(OUT_LINES, "w", encoding="utf-8") as f:
        f.write(f"高压走廊搜索: 共 {len(lines)} 条终点线\n")
        f.write("排序: 走廊长度(狼唯一正招次数) > 羊最小裕度 > 狼平均败着数\n")
        f.write("=" * 78 + "\n")
        shown = 0
        for path in lines:
            corr, mins, avgnl = line_info(path)
            if shown >= 80:
                break
            shown += 1
            f.write(f"[{shown}] 走廊{corr}手狼 羊最小裕度{mins} "
                    f"狼平均败着{avgnl:.1f}\n")
            seq = ["狼C5→C3吃"]
            for who, mv, _x in path:
                if who == "羊":
                    seq.append(f"羊{pos_name(mv[0])}→{pos_name(mv[1])}")
                else:
                    seq.append(f"狼{pos_name(mv[0])}→{pos_name(mv[1])}"
                               f"{'吃' if mv[2] else ''}")
            f.write("    " + " ".join(seq) + "\n")

    # 开局书:羊走局面 -> 该局面所有"保持狼唯一正招"的走法(按线路走廊长度)
    for path in lines:
        corr, mins, avgnl = line_info(path)
        w, s = apply_wolf_move(INIT_WOLVES, INIT_SHEEP, 2, 12)
        for who, mv, marg in path:
            if who == "羊":
                key = f"{w}:{s}"
                lst = book.setdefault(key, {})
                m = (mv[0], mv[1])
                old = lst.get(m)
                if old is None or corr > old:
                    lst[m] = corr
                w2, s2 = apply_sheep_move(w, s, mv[0], mv[1])
            else:
                w2, s2 = apply_wolf_move(w, s, mv[0], mv[1])
            w, s = w2, s2
    book_out = {}
    for k, lst in book.items():
        book_out[k] = sorted([[a, b, c] for (a, b), c in lst.items()],
                             key=lambda x: -x[2])
    with open(OUT_BOOK, "w", encoding="utf-8") as f:
        json.dump(book_out, f, ensure_ascii=False, indent=1)
    print(f"书条目(局面数): {len(book_out)}  写入 {OUT_BOOK}")
    print(f"线路清单: {OUT_LINES}")


if __name__ == "__main__":
    main()

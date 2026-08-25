# -*- coding: utf-8 -*-
"""破解完成后的报告:开局胜负、破解线、分层统计、必败阈值"""
import numpy as np
from numba import njit, prange

import rules
import endgame
import endgame_full as EF
from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, ONGOING,
                   INIT_WOLVES, INIT_SHEEP, popcount, apply_wolf_move,
                   apply_sheep_move, pos_name)
from index import (WOLF_MASKS, FREECELLS, FREELIST, CTAB_FLAT, C22K, PLACEOFF_C,
                   M_CANON, WR_OF_DENSE, WDEN, MIRROR_WR, MIRROR_CELL)
from engine import Engine


@njit(cache=True, parallel=True)
def _layer_stats(kmax, tab, PLACEOFF_C, C22K, WOLF_MASKS, WR_OF_DENSE,
                 FREECELLS, FREELIST, CTAB_FLAT, MIRROR_WR, MIRROR_CELL):
    """每层(羊数)统计规范槽位的狼胜/羊胜/和 数量"""
    stats = np.zeros((kmax - 2, 3), dtype=np.int64)
    for ki in prange(kmax - 2):
        k = ki + 3
        C22k = C22K[ki]
        base = PLACEOFF_C[ki]
        for wd in range(M_CANON):
            wr = WR_OF_DENSE[wd]
            W = WOLF_MASKS[wr]
            for sr in range(C22k):
                S = EF._unrank_sheep(wr, sr, k, FREECELLS, CTAB_FLAT)
                if not EF._slot_canonical(wr, S, CTAB_FLAT, FREELIST,
                                          MIRROR_CELL, MIRROR_WR):
                    continue
                idx = (base + wd * C22k + sr) * 2
                v = tab[idx] & 3
                if v == WOLF_WIN:
                    stats[ki, 0] += 1
                elif v == SHEEP_WIN:
                    stats[ki, 1] += 1
                else:
                    stats[ki, 2] += 1
                v2 = tab[idx + 1] & 3
                if v2 == WOLF_WIN:
                    stats[ki, 0] += 1
                elif v2 == SHEEP_WIN:
                    stats[ki, 1] += 1
                else:
                    stats[ki, 2] += 1
    return stats


def main():
    loaded = endgame.load_tables()
    if endgame._FULL is None:
        print("未找到全破解表,先运行 python solver/endgame_full.py 15")
        raise SystemExit(1)
    tab = endgame._FULL
    dist = endgame._FULL_DIST
    eng = Engine()

    print("=" * 60)
    print("狼吃羊棋 破解报告")
    print("=" * 60)

    # 1) 开局判定
    v0 = endgame.lookup(INIT_WOLVES, INIT_SHEEP, WOLF)
    d0 = endgame.lookup_dist(INIT_WOLVES, INIT_SHEEP, WOLF)
    name = {WOLF_WIN: "狼必胜", SHEEP_WIN: "羊必胜", DRAW: "和棋"}[v0]
    print(f"\n开局(狼先手)判定: 【{name}】  距终局 {d0} 步(双方最优)")
    print(f"  意味着:{'无论羊怎么走,狼都必胜' if v0 == WOLF_WIN else ('无论狼怎么走,羊都必胜' if v0 == SHEEP_WIN else '双方完美走子谁也赢不了,是和棋')}")

    # 2) 破解线
    print("\n破解线(沿最优走法):")
    w, s, t = INIT_WOLVES, INIT_SHEEP, WOLF
    seen = set()
    for step in range(200):
        key = (w, s, t)
        if key in seen:
            print("  (循环)")
            break
        seen.add(key)
        if popcount(s) <= 3:
            print(f"  => 狼胜(羊剩3只)")
            break
        v = endgame.lookup(w, s, t)
        d = endgame.lookup_dist(w, s, t)
        if v == DRAW:
            print(f"  [{step//2+1}. {('狼' if t==WOLF else '羊')}] 和棋局面")
            break
        mv, info = eng.best_move(w, s, t, ())
        if mv is None:
            break
        frm, to, cap = mv
        who = "狼" if t == WOLF else "羊"
        tag = "吃!" if cap else ""
        print(f"  {step+1:3d}. {who} {pos_name(frm)}→{pos_name(to)}{tag}  "
              f"(距终局 {d})")
        if t == WOLF:
            w, s = apply_wolf_move(w, s, frm, to)
        else:
            w, s = apply_sheep_move(w, s, frm, to)
        if not rules.wolf_moves(w, s) and popcount(s) > 2:
            print(f"  => 羊胜(狼被围死)")
            break
        t = 1 - t

    # 3) 分层统计
    print("\n分层统计(规范空间,含两回合):")
    stats = _layer_stats(15, tab, PLACEOFF_C, C22K, WOLF_MASKS, WR_OF_DENSE,
                         FREECELLS, FREELIST, CTAB_FLAT, MIRROR_WR, MIRROR_CELL)
    print(f"  {'羊数':>4} {'狼胜':>14} {'羊胜':>12} {'和棋':>12} {'狼胜占比':>10}")
    for ki in range(13):
        k = ki + 3
        nw, ns, nd = stats[ki]
        tot = nw + ns + nd
        print(f"  {k:>4} {nw:>14,} {ns:>12,} {nd:>12,} {nw/tot*100:>9.1f}%")

    # 4) 必败阈值:羊数 <= 多少时,狼(轮到谁走都)必胜?
    print("\n必败阈值分析(全部局面为狼胜的最小羊数):")
    for ki in range(13):
        k = ki + 3
        nw, ns, nd = stats[ki]
        tot = nw + ns + nd
        if ns == 0 and nd == 0:
            print(f"  羊数 {k}: 全部 {tot:,} 个局面均为狼胜(羊必败)")
        else:
            print(f"  羊数 {k}: 狼胜 {nw:,} ({nw/tot*100:.1f}%), "
                  f"羊胜 {ns:,}, 和棋 {nd:,}")
    print("\n报告完成")


if __name__ == "__main__":
    main()

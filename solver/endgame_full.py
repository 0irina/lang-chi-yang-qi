# -*- coding: utf-8 -*-
"""狼吃羊棋 全局面破解器 —— 镜像压缩 + 2bit/6bit 打包 + 磁盘队列

状态空间压缩:
  * 左右镜像对称:每对镜像摆法只存一个规范代表(狼位 rank 取较小者)。
    规范摆法约 1175×ΣC(22,k) ≈ 47.9 亿,乘 2 回合 ≈ 95.9 亿状态。
  * 每个状态 1 字节:低 2 位 = 胜负(0未定/1狼胜/2羊胜/3和),高 6 位 = 计数器
    (0..62,63=未初始化;最大后继数 60 放得下)。
  * 队列用磁盘 memmap(uint64,约 77GB),距离表用磁盘 memmap(uint16,约 19GB)。
  * 求解支持断点续跑(定期把内存表落盘 + 保存队列水位)。

算法与 endgame.py 相同(终局种子 + 逆向传播 + 计数器全称量词),区别只是索引空间。
终局种子:羊剩 3 只即狼胜(新规则,双方回合均终局);狼无路可走=羊胜;羊无路可走=狼胜。
k=4 时任一吃子落到 k=3 终局,由传播自然处理。
"""
import os
import time

import numpy as np
from numba import njit, prange

import rules
from rules import WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, ONGOING, ALL_MASK
from index import (WOLF_MASKS, FREECELLS, FREELIST, CTAB_FLAT, C,
                   N_FREE, N_CELLS, N_WOLF_COMB,
                   C22K, PLACEOFF_C, M_CANON, WR_OF_DENSE,
                   MIRROR_WR, MIRROR_CELL, WDEN)

_NEIGH = np.full((25, 4), -1, dtype=np.int8)
for p in range(25):
    for i, q in enumerate(rules.NEIGH[p]):
        _NEIGH[p, i] = q
NEIGH = _NEIGH

# ---------------- 基础 ----------------
@njit(cache=True, inline='always')
def _lsb_pos(x):
    p = 0
    while x > 1:
        x = x >> 1
        p += 1
    return p


@njit(cache=True, inline='always')
def _pc(x):
    n = 0
    while x:
        x = x & (x - 1)
        n += 1
    return n


# ---------------- 走法生成 ----------------
@njit(cache=True)
def _wolf_succs(W, S, Wout, Sout, capout, NEIGH):
    empty = ~(W | S) & ALL_MASK
    n = 0
    x = W
    while x:
        lsb = x & -x
        p = _lsb_pos(lsb)
        x = x ^ lsb
        r = p // 5
        c = p % 5
        for i in range(4):
            q = NEIGH[p, i]
            if q >= 0 and ((empty >> q) & 1):
                Wout[n] = (W ^ lsb) | (1 << q)
                Sout[n] = S
                capout[n] = 0
                n += 1
        if r >= 2:
            mid = p - 5
            tgt = p - 10
            if ((empty >> mid) & 1) and ((S >> tgt) & 1):
                Wout[n] = (W ^ lsb) | (1 << tgt)
                Sout[n] = S & ~(1 << tgt)
                capout[n] = 1
                n += 1
        if r <= 2:
            mid = p + 5
            tgt = p + 10
            if ((empty >> mid) & 1) and ((S >> tgt) & 1):
                Wout[n] = (W ^ lsb) | (1 << tgt)
                Sout[n] = S & ~(1 << tgt)
                capout[n] = 1
                n += 1
        if c >= 2:
            mid = p - 1
            tgt = p - 2
            if ((empty >> mid) & 1) and ((S >> tgt) & 1):
                Wout[n] = (W ^ lsb) | (1 << tgt)
                Sout[n] = S & ~(1 << tgt)
                capout[n] = 1
                n += 1
        if c <= 2:
            mid = p + 1
            tgt = p + 2
            if ((empty >> mid) & 1) and ((S >> tgt) & 1):
                Wout[n] = (W ^ lsb) | (1 << tgt)
                Sout[n] = S & ~(1 << tgt)
                capout[n] = 1
                n += 1
    return n


@njit(cache=True)
def _sheep_succs(W, S, Sout, NEIGH):
    empty = ~(W | S) & ALL_MASK
    n = 0
    x = S
    while x:
        lsb = x & -x
        p = _lsb_pos(lsb)
        x = x ^ lsb
        for i in range(4):
            q = NEIGH[p, i]
            if q >= 0 and ((empty >> q) & 1):
                Sout[n] = (S ^ lsb) | (1 << q)
                n += 1
    return n


@njit(cache=True)
def _sheep_uniq_count(W, S, PLACEOFF_C, C22K, CTAB_FLAT, FREELIST,
                      WDEN, MIRROR_WR, MIRROR_CELL, NEIGH, Sout, seen):
    """羊后继的去重规范数量(镜像对坍缩为一个规范后继,弹出时只减一次)"""
    n = _sheep_succs(W, S, Sout, NEIGH)
    m = 0
    for i in range(n):
        e = _encode_c(W, Sout[i], WOLF, PLACEOFF_C, C22K, CTAB_FLAT, FREELIST,
                      WDEN, MIRROR_WR, MIRROR_CELL)
        dup = False
        for j in range(m):
            if seen[j] == e:
                dup = True
                break
        if not dup:
            seen[m] = e
            m += 1
    return m


@njit(cache=True)
def _wolf_uniq_count(W, S, k, PLACEOFF_C, C22K, CTAB_FLAT, FREELIST,
                     WDEN, MIRROR_WR, MIRROR_CELL, NEIGH, Wout, Sout, capout, seen):
    """狼后继的去重规范数量。新规则下 k=3 狼局面全是终局狼胜(永不弹出),
    其吃子到 k=2 的后继不存在于表中:k==3 分支仅作防御,正常路径 k>=4 的
    吃子落到 k=3 终局(表中种子值=狼胜),按普通后继计入、永不递减,语义正确。"""
    n = _wolf_succs(W, S, Wout, Sout, capout, NEIGH)
    m = 0
    for i in range(n):
        if capout[i] and k == 3:
            m += 1  # 终局后继永不弹出,永不递减;按1计保证计数只多不少
            continue
        e = _encode_c(Wout[i], Sout[i], SHEEP, PLACEOFF_C, C22K, CTAB_FLAT,
                      FREELIST, WDEN, MIRROR_WR, MIRROR_CELL)
        dup = False
        for j in range(m):
            if seen[j] == e:
                dup = True
                break
        if not dup:
            seen[m] = e
            m += 1
    return m


@njit(cache=True)
def _has_wolf_move(W, S, NEIGH):
    empty = ~(W | S) & ALL_MASK
    x = W
    while x:
        lsb = x & -x
        p = _lsb_pos(lsb)
        x = x ^ lsb
        r = p // 5
        c = p % 5
        for i in range(4):
            q = NEIGH[p, i]
            if q >= 0 and ((empty >> q) & 1):
                return True
        if r >= 2 and ((empty >> (p - 5)) & 1) and ((S >> (p - 10)) & 1):
            return True
        if r <= 2 and ((empty >> (p + 5)) & 1) and ((S >> (p + 10)) & 1):
            return True
        if c >= 2 and ((empty >> (p - 1)) & 1) and ((S >> (p - 2)) & 1):
            return True
        if c <= 2 and ((empty >> (p + 1)) & 1) and ((S >> (p + 2)) & 1):
            return True
    return False


@njit(cache=True)
def _has_wolf_capture(W, S, NEIGH):
    empty = ~(W | S) & ALL_MASK
    x = W
    while x:
        lsb = x & -x
        p = _lsb_pos(lsb)
        x = x ^ lsb
        r = p // 5
        c = p % 5
        if r >= 2 and ((empty >> (p - 5)) & 1) and ((S >> (p - 10)) & 1):
            return True
        if r <= 2 and ((empty >> (p + 5)) & 1) and ((S >> (p + 10)) & 1):
            return True
        if c >= 2 and ((empty >> (p - 1)) & 1) and ((S >> (p - 2)) & 1):
            return True
        if c <= 2 and ((empty >> (p + 1)) & 1) and ((S >> (p + 2)) & 1):
            return True
    return False


@njit(cache=True)
def _has_sheep_move(W, S, NEIGH):
    empty = ~(W | S) & ALL_MASK
    x = S
    while x:
        lsb = x & -x
        p = _lsb_pos(lsb)
        x = x ^ lsb
        for i in range(4):
            q = NEIGH[p, i]
            if q >= 0 and ((empty >> q) & 1):
                return True
    return False


# ---------------- 前驱生成 ----------------
@njit(cache=True)
def _preds_sheep_turn(W, S, Wout, Sout, NEIGH):
    n = 0
    x = S
    while x:
        lsb = x & -x
        q = _lsb_pos(lsb)
        x = x ^ lsb
        for i in range(4):
            p = NEIGH[q, i]
            if p >= 0 and ((W >> p) & 1) == 0 and ((S >> p) & 1) == 0:
                Wout[n] = W
                Sout[n] = (S ^ lsb) | (1 << p)
                n += 1
    return n


@njit(cache=True)
def _preds_wolf_turn(W, S, Wout, Sout, NEIGH, kmax):
    n = 0
    empty = ~(W | S) & ALL_MASK
    kS = _pc(S)
    x = W
    while x:
        lsb = x & -x
        q = _lsb_pos(lsb)
        x = x ^ lsb
        r = q // 5
        c = q % 5
        for i in range(4):
            p = NEIGH[q, i]
            if p >= 0 and ((empty >> p) & 1):
                Wout[n] = (W ^ lsb) | (1 << p)
                Sout[n] = S
                n += 1
        if kS < kmax:
            if r >= 2:
                mid = q - 5
                p = q - 10
                if ((empty >> mid) & 1) and ((empty >> p) & 1):
                    Wout[n] = (W ^ lsb) | (1 << p)
                    Sout[n] = S | lsb
                    n += 1
            if r <= 2:
                mid = q + 5
                p = q + 10
                if ((empty >> mid) & 1) and ((empty >> p) & 1):
                    Wout[n] = (W ^ lsb) | (1 << p)
                    Sout[n] = S | lsb
                    n += 1
            if c >= 2:
                mid = q - 1
                p = q - 2
                if ((empty >> mid) & 1) and ((empty >> p) & 1):
                    Wout[n] = (W ^ lsb) | (1 << p)
                    Sout[n] = S | lsb
                    n += 1
            if c <= 2:
                mid = q + 1
                p = q + 2
                if ((empty >> mid) & 1) and ((empty >> p) & 1):
                    Wout[n] = (W ^ lsb) | (1 << p)
                    Sout[n] = S | lsb
                    n += 1
    return n


# ---------------- 规范空间编解码 ----------------
@njit(cache=True, inline='always')
def _rank_wolf(W, CTAB_FLAT):
    wr = 0
    t = 1
    x = W
    while x:
        lsb = x & -x
        p = _lsb_pos(lsb)
        x = x ^ lsb
        wr += CTAB_FLAT[p * 16 + t]
        t += 1
    return wr


@njit(cache=True, inline='always')
def _rank_sheep(SS, wr, CTAB_FLAT, FREELIST):
    sr = 0
    t = 1
    x = SS
    while x:
        lsb = x & -x
        p = _lsb_pos(lsb)
        x = x ^ lsb
        j = FREELIST[wr, p]
        sr += CTAB_FLAT[j * 16 + t]
        t += 1
    return sr


@njit(cache=True, inline='always')
def _mirror_mask(m, MIRROR_CELL):
    r = 0
    x = m
    while x:
        lsb = x & -x
        p = _lsb_pos(lsb)
        x = x ^ lsb
        r |= 1 << MIRROR_CELL[p]
    return r


@njit(cache=True)
def _encode_c(W, S, turn, PLACEOFF_C, C22K, CTAB_FLAT, FREELIST,
              WDEN, MIRROR_WR, MIRROR_CELL):
    k = _pc(S)
    ki = k - 3
    wr = _rank_wolf(W, CTAB_FLAT)
    wrm = MIRROR_WR[wr]
    if wr < wrm:
        cwr = wr
        SS = S
    elif wr > wrm:
        cwr = wrm
        SS = _mirror_mask(S, MIRROR_CELL)
    else:
        # 狼形自身镜像对称:局面与"羊位镜像"是同一镜像类,必须坍缩到同一表项
        cwr = wr
        SS = S
        SSm = _mirror_mask(S, MIRROR_CELL)
        if _rank_sheep(SSm, cwr, CTAB_FLAT, FREELIST) < _rank_sheep(SS, cwr, CTAB_FLAT, FREELIST):
            SS = SSm
    wd = WDEN[cwr]
    sr = _rank_sheep(SS, cwr, CTAB_FLAT, FREELIST)
    return (PLACEOFF_C[ki] + wd * C22K[ki] + sr) * 2 + turn


@njit(cache=True)
def _unrank_sheep(wr, rank, K, FREECELLS, CTAB_FLAT):
    x = 0
    r = rank
    j = K
    while j >= 1:
        p = 0
        while CTAB_FLAT[p * 16 + j] <= r:
            p += 1
        p -= 1
        r -= CTAB_FLAT[p * 16 + j]
        x |= 1 << FREECELLS[wr, p]
        j -= 1
    return x


@njit(cache=True)
def _decode_c(idx, PLACEOFF_C, C22K, WOLF_MASKS, WR_OF_DENSE, FREECELLS, CTAB_FLAT):
    turn = idx & 1
    p = idx >> 1
    ki = 12
    while ki > 0 and p < PLACEOFF_C[ki]:
        ki -= 1
    k = ki + 3
    t = p - PLACEOFF_C[ki]
    sr = t % C22K[ki]
    wd = t // C22K[ki]
    wr = WR_OF_DENSE[wd]
    W = WOLF_MASKS[wr]
    S = _unrank_sheep(wr, sr, k, FREECELLS, CTAB_FLAT)
    return W, S, turn, k


@njit(cache=True, inline='always')
def _slot_canonical(wr, S, CTAB_FLAT, FREELIST, MIRROR_CELL, MIRROR_WR):
    """(wr,S) 槽位是否为规范槽:非对称狼形恒真;对称狼形要求 rank(S) <= rank(mirror(S))"""
    if MIRROR_WR[wr] != wr:
        return True
    SSm = _mirror_mask(S, MIRROR_CELL)
    return _rank_sheep(S, wr, CTAB_FLAT, FREELIST) <= _rank_sheep(SSm, wr, CTAB_FLAT, FREELIST)


# ---------------- 种子 ----------------
@njit(cache=True)
def _seed_full(kmax, tab, queue, PLACEOFF_C, C22K, WOLF_MASKS, WR_OF_DENSE,
               FREECELLS, FREELIST, CTAB_FLAT, MIRROR_WR, MIRROR_CELL, NEIGH):
    tail = 0
    for ki in range(kmax - 2):
        k = ki + 3
        C22k = C22K[ki]
        base = PLACEOFF_C[ki]
        for wd in range(M_CANON):
            wr = WR_OF_DENSE[wd]
            W = WOLF_MASKS[wr]
            for sr in range(C22k):
                S = _unrank_sheep(wr, sr, k, FREECELLS, CTAB_FLAT)
                if not _slot_canonical(wr, S, CTAB_FLAT, FREELIST, MIRROR_CELL, MIRROR_WR):
                    continue
                idx = (base + wd * C22k + sr) * 2
                if k == 3:
                    # 新规则:羊剩3只=狼胜,双方回合均为终局(先于走法检查)
                    tab[idx] = WOLF_WIN
                    queue[tail] = idx
                    tail += 1
                    tab[idx + 1] = WOLF_WIN
                    queue[tail] = idx + 1
                    tail += 1
                else:
                    if not _has_wolf_move(W, S, NEIGH):
                        tab[idx] = SHEEP_WIN
                        queue[tail] = idx
                        tail += 1
                    if not _has_sheep_move(W, S, NEIGH):
                        tab[idx + 1] = WOLF_WIN
                        queue[tail] = idx + 1
                        tail += 1
    return tail


# ---------------- 传播(分步,由 Python 驱动做断点) ----------------
@njit(cache=True)
def _propagate_step(kmax, tab, dist, queue, head, tail, max_steps, PLACEOFF_C,
                    C22K, WOLF_MASKS, WR_OF_DENSE, FREECELLS, FREELIST, CTAB_FLAT,
                    WDEN, MIRROR_WR, MIRROR_CELL, NEIGH):
    predW = np.empty(64, dtype=np.int64)
    predS = np.empty(64, dtype=np.int64)
    succW = np.empty(64, dtype=np.int64)
    succS = np.empty(64, dtype=np.int64)
    succcap = np.empty(64, dtype=np.int8)
    seen = np.empty(64, dtype=np.int64)
    seen2 = np.empty(64, dtype=np.int64)
    processed = 0
    while head < tail and processed < max_steps:
        X = queue[head]
        head += 1
        b = tab[X]
        v = b & 3
        turn = X & 1
        dX = dist[X]
        nd = dX + 1
        if nd > 65535:
            nd = 65535
        W, S, t, k = _decode_c(X, PLACEOFF_C, C22K, WOLF_MASKS, WR_OF_DENSE,
                               FREECELLS, CTAB_FLAT)
        if turn == WOLF:
            n = _preds_sheep_turn(W, S, predW, predS, NEIGH)
            m = 0
            for i in range(n):
                P = _encode_c(predW[i], predS[i], SHEEP, PLACEOFF_C, C22K,
                              CTAB_FLAT, FREELIST, WDEN, MIRROR_WR, MIRROR_CELL)
                # 规范前驱去重:同一规范后继的弹出只对其减一次
                dup = False
                for j in range(m):
                    if seen[j] == P:
                        dup = True
                        break
                if dup:
                    continue
                seen[m] = P
                m += 1
                bP = tab[P]
                if (bP & 3) != 0:
                    continue
                if v == WOLF_WIN:
                    c = bP >> 2
                    if c == 63:
                        # 去重规范后继总数(与弹出侧去重配平)
                        n2 = _sheep_uniq_count(predW[i], predS[i], PLACEOFF_C,
                                               C22K, CTAB_FLAT, FREELIST, WDEN,
                                               MIRROR_WR, MIRROR_CELL, NEIGH,
                                               succS, seen2)
                        if n2 <= 1:
                            tab[P] = WOLF_WIN
                            dist[P] = nd
                            queue[tail] = P
                            tail += 1
                            continue
                        tab[P] = ((n2 - 1) << 2)
                    else:
                        c -= 1
                        if c == 0:
                            tab[P] = WOLF_WIN
                            dist[P] = nd
                            queue[tail] = P
                            tail += 1
                        else:
                            tab[P] = (c << 2)
                else:
                    tab[P] = SHEEP_WIN
                    dist[P] = nd
                    queue[tail] = P
                    tail += 1
        else:
            n = _preds_wolf_turn(W, S, predW, predS, NEIGH, kmax)
            m = 0
            for i in range(n):
                P = _encode_c(predW[i], predS[i], WOLF, PLACEOFF_C, C22K,
                              CTAB_FLAT, FREELIST, WDEN, MIRROR_WR, MIRROR_CELL)
                # 规范前驱去重
                dup = False
                for j in range(m):
                    if seen[j] == P:
                        dup = True
                        break
                if dup:
                    continue
                seen[m] = P
                m += 1
                bP = tab[P]
                if (bP & 3) != 0:
                    continue
                if v == SHEEP_WIN:
                    c = bP >> 2
                    if c == 63:
                        # 去重规范后继总数;k=4 的吃子落到 k=3 终局(表中种子狼胜),
                        n2 = _wolf_uniq_count(predW[i], predS[i], k, PLACEOFF_C,
                                              C22K, CTAB_FLAT, FREELIST, WDEN,
                                              MIRROR_WR, MIRROR_CELL, NEIGH,
                                              succW, succS, succcap, seen2)
                        if n2 <= 1:
                            tab[P] = SHEEP_WIN
                            dist[P] = nd
                            queue[tail] = P
                            tail += 1
                            continue
                        tab[P] = ((n2 - 1) << 2)
                    else:
                        c -= 1
                        if c == 0:
                            tab[P] = SHEEP_WIN
                            dist[P] = nd
                            queue[tail] = P
                            tail += 1
                        else:
                            tab[P] = (c << 2)
                else:
                    tab[P] = WOLF_WIN
                    dist[P] = nd
                    queue[tail] = P
                    tail += 1
        processed += 1
    return head, tail, processed


# ---------------- 独立复核 ----------------
@njit(cache=True)
def _verify_full(kmax, N, tab, PLACEOFF_C, C22K, WOLF_MASKS, WR_OF_DENSE,
                 FREECELLS, FREELIST, CTAB_FLAT, WDEN, MIRROR_WR, MIRROR_CELL, NEIGH):
    bads = np.zeros(kmax - 2, dtype=np.int64)
    Wout = np.empty(64, dtype=np.int64)
    Sout = np.empty(64, dtype=np.int64)
    capout = np.empty(64, dtype=np.int8)
    for ki in range(kmax - 2):
        k = ki + 3
        C22k = C22K[ki]
        base = PLACEOFF_C[ki]
        for wd in range(M_CANON):
            wr = WR_OF_DENSE[wd]
            W = WOLF_MASKS[wr]
            for sr in range(C22k):
                S = _unrank_sheep(wr, sr, k, FREECELLS, CTAB_FLAT)
                if not _slot_canonical(wr, S, CTAB_FLAT, FREELIST, MIRROR_CELL, MIRROR_WR):
                    continue
                idx = (base + wd * C22k + sr) * 2
                if k == 3:
                    # 新规则:羊剩3只=狼胜,双方回合均终局,直接核对种子值
                    if (tab[idx] & 3) != WOLF_WIN:
                        bads[ki] += 1
                    if (tab[idx + 1] & 3) != WOLF_WIN:
                        bads[ki] += 1
                    continue
                n = _wolf_succs(W, S, Wout, Sout, capout, NEIGH)
                if n == 0:
                    exp = SHEEP_WIN
                else:
                    has_win = False
                    all_lose = True
                    for i in range(n):
                        # 新规则:吃子落到 k=3 终局,其种子值=狼胜,查表即可
                        sv = tab[_encode_c(Wout[i], Sout[i], SHEEP, PLACEOFF_C,
                                           C22K, CTAB_FLAT, FREELIST, WDEN,
                                           MIRROR_WR, MIRROR_CELL)] & 3
                        if sv == WOLF_WIN:
                            has_win = True
                        if sv != SHEEP_WIN:
                            all_lose = False
                    if has_win:
                        exp = WOLF_WIN
                    elif all_lose:
                        exp = SHEEP_WIN
                    else:
                        exp = DRAW
                if (tab[idx] & 3) != exp:
                    bads[ki] += 1
                n2 = _sheep_succs(W, S, Sout, NEIGH)
                if n2 == 0:
                    exp2 = WOLF_WIN
                else:
                    has_win = False
                    all_lose = True
                    for i in range(n2):
                        sv = tab[_encode_c(W, Sout[i], WOLF, PLACEOFF_C, C22K,
                                           CTAB_FLAT, FREELIST, WDEN,
                                           MIRROR_WR, MIRROR_CELL)] & 3
                        if sv == SHEEP_WIN:
                            has_win = True
                        if sv != WOLF_WIN:
                            all_lose = False
                    if has_win:
                        exp2 = SHEEP_WIN
                    elif all_lose:
                        exp2 = WOLF_WIN
                    else:
                        exp2 = DRAW
                if (tab[idx + 1] & 3) != exp2:
                    bads[ki] += 1
    return bads.sum()


# ---------------- 收尾:未定=和棋 + 统计(原地,避免大临时数组) ----------------
@njit(cache=True)
def _finalize(tab, N):
    nw = 0
    ns = 0
    nd = 0
    for i in range(N):
        b = tab[i]
        if (b & 3) == 0:
            tab[i] = (b & 0xFC) | DRAW
            nd += 1
        elif (b & 3) == WOLF_WIN:
            nw += 1
        else:
            ns += 1
    return nw, ns, nd


# ---------------- 驱动 ----------------
def _save_atomic(arr, path):
    tmp = path + ".tmp.npy"  # 必须以 .npy 结尾,否则 np.save 会自行追加后缀
    np.save(tmp, arr)
    os.replace(tmp, path)


def _load_checkpoint_pair(tab_path, meta_path):
    """按'表先存、水位后存'的先后关系配对,返回 (存档表路径, head, tail)。
    若主存档错位(表比水位新),自动回退上一代,保证配对一致。"""
    tab_prev = tab_path + ".prev"
    meta_prev = meta_path + ".prev"

    def pair_ok(t, m):
        return (os.path.exists(t) and os.path.exists(m)
                and os.path.getmtime(t) <= os.path.getmtime(m))

    for t, m in ((tab_path, meta_path), (tab_prev, meta_path),
                 (tab_prev, meta_prev)):
        if pair_ok(t, m):
            try:
                meta = np.load(m)
                return t, int(meta[0]), int(meta[1])
            except Exception:
                continue
    # 兜底:允许等时间戳(旧版协议)或任意可加载组合
    for t, m in ((tab_path, meta_path), (tab_prev, meta_prev)):
        if os.path.exists(t) and os.path.exists(m):
            try:
                meta = np.load(m)
                return t, int(meta[0]), int(meta[1])
            except Exception:
                continue
    raise RuntimeError("找不到可用的破解存档")


def _checkpoint(tab, head, tail, tab_path, meta_path, queue, dist):
    """双代轮换存档:先轮换表,再轮换水位。任何时刻磁盘上都保留一致的一代。"""
    tab_prev = tab_path + ".prev"
    meta_prev = meta_path + ".prev"
    if os.path.exists(tab_prev):
        os.remove(tab_prev)
    if os.path.exists(tab_path):
        os.replace(tab_path, tab_prev)
    _save_atomic(tab, tab_path)
    if os.path.exists(meta_prev):
        os.remove(meta_prev)
    if os.path.exists(meta_path):
        os.replace(meta_path, meta_prev)
    _save_atomic(np.array([head, tail], dtype=np.int64), meta_path)
    queue.flush()
    dist.flush()


def default_outdir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "tt")


def full_size(kmax):
    ki = kmax - 3
    placements = int(PLACEOFF_C[ki]) + M_CANON * int(C22K[ki])
    return placements * 2


def solve_full(kmax=15, outdir=None, resume=False, checkpoint_s=1800,
               verify=True):
    """全局面破解。resume=True 时从断点续跑。"""
    if outdir is None:
        outdir = default_outdir()
    os.makedirs(outdir, exist_ok=True)
    N = full_size(kmax)
    tab_path = os.path.join(outdir, "full_packed.npy")
    live_path = os.path.join(outdir, "full_live.dat")
    queue_path = os.path.join(outdir, "full_queue.dat")
    dist_path = os.path.join(outdir, "full_dist.dat")
    meta_path = os.path.join(outdir, "full_meta.npy")

    if resume:
        # 存档可能位于 .prev(轮换协议),两者皆可;找不到就报错,绝不误开新局
        if not ((os.path.exists(tab_path) or os.path.exists(tab_path + ".prev"))
                and os.path.exists(meta_path)):
            raise RuntimeError("resume 模式找不到可用存档,已拒绝重新开始(防止误删队列)")
        used, head, tail = _load_checkpoint_pair(tab_path, meta_path)
        # 顺序读盘加载成内存数组:启动快(SSD 顺序读),传播阶段满速(无缺页)
        t0 = time.time()
        tab = np.load(used)
        queue = np.memmap(queue_path, dtype=np.uint64, mode="r+", shape=(N,))
        dist = np.memmap(dist_path, dtype=np.uint16, mode="r+", shape=(N,))
        print(f"[续跑] 存档={os.path.basename(used)} 头={head:,} 尾={tail:,} "
              f"加载={time.time()-t0:.1f}s", flush=True)
    else:
        tab = np.full(N, (63 << 2), dtype=np.uint8)
        queue = np.memmap(queue_path, dtype=np.uint64, mode="w+", shape=(N,))
        dist = np.memmap(dist_path, dtype=np.uint16, mode="w+", shape=(N,))
        head = 0
        t0 = time.time()
        tail = _seed_full(kmax, tab, queue, PLACEOFF_C, C22K, WOLF_MASKS,
                          WR_OF_DENSE, FREECELLS, FREELIST, CTAB_FLAT,
                          MIRROR_WR, MIRROR_CELL, NEIGH)
        print(f"[种子] 入队={tail:,}  用时={time.time()-t0:.1f}s", flush=True)

    t0 = time.time()
    last = t0
    processed_total = 0
    while head < tail:
        head, tail, p = _propagate_step(kmax, tab, dist, queue, head, tail,
                                        200_000, PLACEOFF_C, C22K, WOLF_MASKS,
                                        WR_OF_DENSE, FREECELLS, FREELIST,
                                        CTAB_FLAT, WDEN, MIRROR_WR, MIRROR_CELL, NEIGH)
        processed_total += p
        now = time.time()
        if now - last >= checkpoint_s or head >= tail:
            last = now
            _checkpoint(tab, head, tail, tab_path, meta_path, queue, dist)
            rate = processed_total / max(1e-9, now - t0)
            eta_h = (tail - head) / max(1e-9, rate) / 3600
            print(f"  [进度] 已处理={processed_total:,}  剩余队列={tail-head:,}  "
                  f"速率={rate:,.0f}/s  预计剩余={eta_h:.1f}h", flush=True)

    # 未定 = 和棋(原地标记并统计)
    t2 = time.time()
    nw, ns, nd = _finalize(tab, N)
    counts = (nw, ns, nd)
    _checkpoint(tab, head, tail, tab_path, meta_path, queue, dist)
    print(f"求解完成: 狼胜={counts[0]:,} 羊胜={counts[1]:,} 和={counts[2]:,} "
          f"传播用时={(t2-t0)/3600:.2f}h", flush=True)
    bad = None
    if verify:
        print("开始独立复核...", flush=True)
        t3 = time.time()
        bad = _verify_full(kmax, N, tab, PLACEOFF_C, C22K, WOLF_MASKS,
                           WR_OF_DENSE, FREECELLS, FREELIST, CTAB_FLAT, WDEN,
                           MIRROR_WR, MIRROR_CELL, NEIGH)
        print(f"复核完成: 错误={bad}  用时={(time.time()-t3)/60:.1f}min", flush=True)
    # 只有复核通过(或跳过复核)才写完成标志,查询侧凭标志启用全表
    if bad is None or bad == 0:
        with open(os.path.join(outdir, "full_done.flag"), "w") as f:
            f.write("done\n")
    return dict(N=N, wolf=counts[0], sheep=counts[1], draw=counts[2],
                solve_h=(t2 - t0) / 3600, bad=bad)


if __name__ == "__main__":
    import sys
    km = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    resume = "--resume" in sys.argv
    solve_full(km, resume=resume)

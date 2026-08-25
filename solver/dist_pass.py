# -*- coding: utf-8 -*-
"""精确距离修正:顺序波次传播,重算全部胜/负局面的"到终局精确步数"

为什么需要:并行版的 dist 因块内事件乱序而系统性偏小(平均约 -11 步),
导致 AI 在必胜局面里"绕圈不杀"。本模块用顺序 FIFO(BFS 波次)重新传播距离,
波次顺序保证:min 分支先到者即最小,max 分支计数器归零时即最大,dist 严格精确。

原理:胜负值已定(不动);仅在同一胜负类内部传播距离。
  种子 dist=0:狼回合无路可走(羊胜)/ 羊回合无路可走(狼胜)/ k=3 双方回合(狼胜,新规则)。
  传播:X(dist=d) 弹出,对每个同类前驱 P:
    * min 分支(狼回合狼胜 / 羊回合羊胜):首次事件即定 dist=1+min(波次保证最小)
    * max 分支(羊回合狼胜 / 狼回合羊胜):计数器(同类后继去重计数)归零时定
      dist=1+max(波次保证最后到达者即最大)
计数器复用 tab 字节的高 6 位(值位不动),0 表示"已定距离"。
支持断点续跑(与主破解相同的双代轮换存档)。
"""
import os
import time

import numpy as np
from numba import njit

import rules
from rules import WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, ONGOING, ALL_MASK
from index import (WOLF_MASKS, FREECELLS, FREELIST, CTAB_FLAT, C22K, PLACEOFF_C,
                   M_CANON, WR_OF_DENSE, MIRROR_WR, MIRROR_CELL, WDEN)
import endgame_full as EF
from endgame_full import (_encode_c, _decode_c, _preds_sheep_turn, _preds_wolf_turn,
                          _sheep_succs, _wolf_succs, _has_wolf_move,
                          _has_sheep_move, _has_wolf_capture, _slot_canonical,
                          _unrank_sheep, _checkpoint, _load_checkpoint_pair,
                          full_size, default_outdir, NEIGH)


# ---------------- 同类后继去重计数 ----------------
@njit(cache=True)
def _sheep_uniq_cls(W, S, cls, tab, PLACEOFF_C, C22K, CTAB_FLAT, FREELIST,
                    WDEN, MIRROR_WR, MIRROR_CELL, NEIGH, Sout, seen):
    n = _sheep_succs(W, S, Sout, NEIGH)
    m = 0
    for i in range(n):
        e = _encode_c(W, Sout[i], WOLF, PLACEOFF_C, C22K, CTAB_FLAT, FREELIST,
                      WDEN, MIRROR_WR, MIRROR_CELL)
        if (tab[e] & 3) != cls:
            continue
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
def _wolf_uniq_cls(W, S, k, cls, tab, PLACEOFF_C, C22K, CTAB_FLAT, FREELIST,
                   WDEN, MIRROR_WR, MIRROR_CELL, NEIGH, Wout, Sout, capout, seen):
    n = _wolf_succs(W, S, Wout, Sout, capout, NEIGH)
    m = 0
    for i in range(n):
        if capout[i]:
            if k == 3:
                sv = WOLF_WIN  # 吃剩2只终局
            else:
                e = _encode_c(Wout[i], Sout[i], SHEEP, PLACEOFF_C, C22K,
                              CTAB_FLAT, FREELIST, WDEN, MIRROR_WR, MIRROR_CELL)
                sv = tab[e] & 3
        else:
            e = _encode_c(Wout[i], Sout[i], SHEEP, PLACEOFF_C, C22K,
                          CTAB_FLAT, FREELIST, WDEN, MIRROR_WR, MIRROR_CELL)
            sv = tab[e] & 3
        if sv != cls:
            continue
        if capout[i] and k == 3:
            m += 1  # 终局后继永不再弹出,但同类则计入 max 分支(不可能:羊胜类不含它)
            continue
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
def _reset_counters(tab, N):
    """计数器位复位为未初始化(63),值位不动;原地执行,零临时内存"""
    for i in range(N):
        tab[i] = (tab[i] & 3) | (63 << 2)


# ---------------- 种子(分块可续跑) ----------------
@njit(cache=True)
def _dist_seed_chunk(kmax, tab, dist, queue, tail, ki, wd, sr, max_steps,
                     PLACEOFF_C, C22K, WOLF_MASKS, WR_OF_DENSE, FREECELLS,
                     FREELIST, CTAB_FLAT, MIRROR_WR, MIRROR_CELL, NEIGH):
    """从 (ki, wd, sr) 继续扫描,最多处理 max_steps 个槽位。
    返回 (ki, wd, sr, tail, done)。"""
    steps = 0
    while ki < kmax - 2:
        k = ki + 3
        C22k = C22K[ki]
        base = PLACEOFF_C[ki]
        while wd < M_CANON:
            wr = WR_OF_DENSE[wd]
            W = WOLF_MASKS[wr]
            while sr < C22k:
                S = _unrank_sheep(wr, sr, k, FREECELLS, CTAB_FLAT)
                if _slot_canonical(wr, S, CTAB_FLAT, FREELIST, MIRROR_CELL,
                                   MIRROR_WR):
                    idx = (base + wd * C22k + sr) * 2
                    if k == 3:
                        # 新规则:k=3 双方回合均终局狼胜,dist=0
                        if (tab[idx] & 3) == WOLF_WIN:
                            dist[idx] = 0
                            tab[idx] = (tab[idx] & 3)
                            queue[tail] = idx
                            tail += 1
                        if (tab[idx + 1] & 3) == WOLF_WIN:
                            dist[idx + 1] = 0
                            tab[idx + 1] = (tab[idx + 1] & 3)
                            queue[tail] = idx + 1
                            tail += 1
                    else:
                        if not _has_wolf_move(W, S, NEIGH):
                            if (tab[idx] & 3) == SHEEP_WIN:
                                dist[idx] = 0
                                tab[idx] = (tab[idx] & 3)
                                queue[tail] = idx
                                tail += 1
                        if not _has_sheep_move(W, S, NEIGH):
                            if (tab[idx + 1] & 3) == WOLF_WIN:
                                dist[idx + 1] = 0
                                tab[idx + 1] = (tab[idx + 1] & 3)
                                queue[tail] = idx + 1
                                tail += 1
                sr += 1
                steps += 1
                if steps >= max_steps:
                    return ki, wd, sr, tail, False
            sr = 0
            wd += 1
        wd = 0
        ki += 1
    return ki, wd, sr, tail, True


@njit(cache=True)
def _restore_seed_markers(tab, queue, tail):
    """续跑:计数器已全复位后,把已入队种子的计数器标记恢复为 0(已定距离)"""
    for i in range(tail):
        X = queue[i]
        tab[X] = tab[X] & 3


# ---------------- 传播 ----------------
@njit(cache=True)
def _dist_step(kmax, tab, dist, queue, head, tail, max_steps, PLACEOFF_C,
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
        v = tab[X] & 3
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
                if (tab[P] & 3) != v:
                    continue
                dup = False
                for u in range(m):
                    if seen[u] == P:
                        dup = True
                        break
                if dup:
                    continue
                seen[m] = P
                m += 1
                c = tab[P] >> 2
                if c == 0:
                    continue  # 已定距离
                if v == WOLF_WIN:
                    # max 分支:羊回合狼胜
                    if c == 63:
                        n2 = _sheep_uniq_cls(predW[i], predS[i], WOLF_WIN, tab,
                                             PLACEOFF_C, C22K, CTAB_FLAT, FREELIST,
                                             WDEN, MIRROR_WR, MIRROR_CELL, NEIGH,
                                             succS, seen2)
                        if n2 <= 1:
                            dist[P] = nd
                            tab[P] = (tab[P] & 3)
                            queue[tail] = P
                            tail += 1
                            continue
                        tab[P] = (tab[P] & 3) | ((n2 - 1) << 2)
                    else:
                        c -= 1
                        if c == 0:
                            dist[P] = nd
                            tab[P] = (tab[P] & 3)
                            queue[tail] = P
                            tail += 1
                        else:
                            tab[P] = (tab[P] & 3) | (c << 2)
                else:
                    # min 分支:羊回合羊胜(首次事件即最小)
                    dist[P] = nd
                    tab[P] = (tab[P] & 3)
                    queue[tail] = P
                    tail += 1
        else:
            n = _preds_wolf_turn(W, S, predW, predS, NEIGH, kmax)
            m = 0
            for i in range(n):
                P = _encode_c(predW[i], predS[i], WOLF, PLACEOFF_C, C22K,
                              CTAB_FLAT, FREELIST, WDEN, MIRROR_WR, MIRROR_CELL)
                if (tab[P] & 3) != v:
                    continue
                dup = False
                for u in range(m):
                    if seen[u] == P:
                        dup = True
                        break
                if dup:
                    continue
                seen[m] = P
                m += 1
                c = tab[P] >> 2
                if c == 0:
                    continue
                if v == SHEEP_WIN:
                    # max 分支:狼回合羊胜
                    if c == 63:
                        n2 = _wolf_uniq_cls(predW[i], predS[i], k, SHEEP_WIN, tab,
                                            PLACEOFF_C, C22K, CTAB_FLAT, FREELIST,
                                            WDEN, MIRROR_WR, MIRROR_CELL, NEIGH,
                                            succW, succS, succcap, seen2)
                        if n2 <= 1:
                            dist[P] = nd
                            tab[P] = (tab[P] & 3)
                            queue[tail] = P
                            tail += 1
                            continue
                        tab[P] = (tab[P] & 3) | ((n2 - 1) << 2)
                    else:
                        c -= 1
                        if c == 0:
                            dist[P] = nd
                            tab[P] = (tab[P] & 3)
                            queue[tail] = P
                            tail += 1
                        else:
                            tab[P] = (tab[P] & 3) | (c << 2)
                else:
                    # min 分支:狼回合狼胜
                    dist[P] = nd
                    tab[P] = (tab[P] & 3)
                    queue[tail] = P
                    tail += 1
        processed += 1
    return head, tail, processed


# ---------------- 驱动 ----------------
def solve_dist(kmax=15, outdir=None, resume=False, checkpoint_s=600):
    if outdir is None:
        outdir = default_outdir()
    N = full_size(kmax)
    tab_path = os.path.join(outdir, "full_packed.npy")
    queue_path = os.path.join(outdir, "full_distq.dat")
    dist_path = os.path.join(outdir, "full_dist.dat")
    meta_path = os.path.join(outdir, "full_dist_meta.npy")
    seed_pos_path = os.path.join(outdir, "dist_seed_pos.npy")

    dist = np.memmap(dist_path, dtype=np.uint16, mode="r+", shape=(N,))
    if not os.path.exists(queue_path):
        q0 = np.memmap(queue_path, dtype=np.uint64, mode="w+", shape=(N,))
        q0.flush()
    queue = np.memmap(queue_path, dtype=np.uint64, mode="r+", shape=(N,))

    if resume:
        if os.path.exists(meta_path):
            # 传播阶段的断点续跑
            used, head, tail = _load_checkpoint_pair(tab_path, meta_path)
            tab = np.load(used)
            print(f"[距离续跑·传播] 存档={os.path.basename(used)} "
                  f"头={head:,} 尾={tail:,}", flush=True)
            ki = wd = sr = 0
        else:
            # 种子阶段的断点续跑:从进度文件恢复(无进度文件则从头开始)
            tab = np.load(tab_path)
            _reset_counters(tab, N)
            if os.path.exists(seed_pos_path):
                pos = np.load(seed_pos_path)
                ki, wd, sr, tail = (int(pos[0]), int(pos[1]),
                                    int(pos[2]), int(pos[3]))
                _restore_seed_markers(tab, queue, tail)
                print(f"[距离续跑·种子] 从 ki={ki} wd={wd} sr={sr} 尾={tail:,} "
                      f"继续", flush=True)
            else:
                ki = wd = sr = tail = 0
                print("[距离续跑·种子] 无进度文件,从头开始", flush=True)
            head = 0
    else:
        tab = np.load(tab_path)
        t0 = time.time()
        _reset_counters(tab, N)
        print(f"[计数器复位] 用时={time.time()-t0:.1f}s", flush=True)
        head = 0
        ki = wd = sr = 0
        tail = 0

    # ---- 种子阶段(分块 + 进度文件,任何中断最多损失一小块) ----
    seed_done = resume and os.path.exists(meta_path)  # 传播续跑说明种子已完成
    if not seed_done:
        while True:
            ki, wd, sr, tail, done = _dist_seed_chunk(
                kmax, tab, dist, queue, tail, ki, wd, sr, 300_000_000,
                PLACEOFF_C, C22K, WOLF_MASKS, WR_OF_DENSE, FREECELLS, FREELIST,
                CTAB_FLAT, MIRROR_WR, MIRROR_CELL, NEIGH)
            np.save(seed_pos_path, np.array([ki, wd, sr, tail], dtype=np.int64))
            queue.flush()
            dist.flush()
            print(f"[种子分块] ki={ki} wd={wd} sr={sr} 入队={tail:,}", flush=True)
            if done:
                break
        print(f"[距离种子完成] 入队={tail:,}", flush=True)

    # ---- 传播阶段 ----
    t0 = time.time()
    last = t0
    processed_total = 0
    while head < tail:
        head, tail, p = _dist_step(kmax, tab, dist, queue, head, tail, 200_000,
                                   PLACEOFF_C, C22K, WOLF_MASKS, WR_OF_DENSE,
                                   FREECELLS, FREELIST, CTAB_FLAT, WDEN,
                                   MIRROR_WR, MIRROR_CELL, NEIGH)
        processed_total += p
        now = time.time()
        if now - last >= checkpoint_s or head >= tail:
            last = now
            _checkpoint(tab, head, tail, tab_path, meta_path, queue, dist)
            rate = processed_total / max(1e-9, now - t0)
            eta_h = (tail - head) / max(1e-9, rate) / 3600
            print(f"  [距离进度] 已处理={processed_total:,} 剩余={tail-head:,} "
                  f"速率={rate:,.0f}/s 预计剩余={eta_h:.1f}h", flush=True)

    _checkpoint(tab, head, tail, tab_path, meta_path, queue, dist)
    with open(os.path.join(outdir, "dist_pass_done.flag"), "w") as f:
        f.write("done\n")
    print(f"精确距离修正完成, 传播用时={(time.time()-t0)/3600:.2f}h", flush=True)


if __name__ == "__main__":
    import sys
    resume = "--resume" in sys.argv
    solve_dist(resume=resume)

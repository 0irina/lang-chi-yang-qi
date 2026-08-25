# -*- coding: utf-8 -*-
"""并行版传播器(无锁分块)——弹出阶段全核并行,应用阶段串行回放

正确性论证:
  * 块边界与顺序版一致:块 c 的"应用"全部完成之后,块 c+1 的"弹出"才开始,
    因此跨块的事件次序与顺序版逐条等价。
  * 块内事件对同一前驱 P 可交换:递减事件可交换;赋值事件优先于递减
    (应用时先检查值,已赋值则跳过);惰性初始化幂等(n2 在弹出阶段并行算好,
    同一 P 的多个事件附带的 n2 相同)。
  * 弹出阶段的 tab[P] 快读(是否已赋值/计数器是否已初始化)是良性竞争:
    应用阶段都会在串行上下文里重新检查。
  * dist(到终局距离)在并行调度下可能比精确值略大;胜负值严格精确。

内存:块大小 20 万状态,每线程事件缓冲约 640k 条 × 30B ≈ 19MB,总计 <400MB。
"""
import os
import time

import numpy as np
from numba import njit, prange, get_thread_id, get_num_threads

import rules
from rules import WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, ONGOING, ALL_MASK
from index import (WOLF_MASKS, FREECELLS, FREELIST, CTAB_FLAT, C22K, PLACEOFF_C,
                   M_CANON, WR_OF_DENSE, MIRROR_WR, MIRROR_CELL, WDEN)
import endgame_full as EF
from endgame_full import (_encode_c, _decode_c, _preds_sheep_turn, _preds_wolf_turn,
                          _sheep_uniq_count, _wolf_uniq_count, _seed_full,
                          _finalize, _verify_full, _checkpoint, _load_checkpoint_pair,
                          full_size, default_outdir, NEIGH)


@njit(cache=True, parallel=True)
def _par_pop_chunk(kmax, tab, dist, queue, head, chunk, evP, evW, evS, evN2,
                   evNd, evCls, evAssign, evCnt, PLACEOFF_C, C22K, WOLF_MASKS,
                   WR_OF_DENSE, FREECELLS, FREELIST, CTAB_FLAT, WDEN, MIRROR_WR,
                   MIRROR_CELL, NEIGH):
    for i in prange(chunk):
        tid = get_thread_id()
        X = queue[head + i]
        b = tab[X]
        v = b & 3
        turn = X & 1
        dX = dist[X]
        nd = dX + 1
        if nd > 65535:
            nd = 65535
        W, S, t, k = _decode_c(X, PLACEOFF_C, C22K, WOLF_MASKS, WR_OF_DENSE,
                               FREECELLS, CTAB_FLAT)
        predW = np.empty(64, dtype=np.int64)
        predS = np.empty(64, dtype=np.int64)
        seen = np.empty(64, dtype=np.int64)
        succW = np.empty(64, dtype=np.int64)
        succS = np.empty(64, dtype=np.int64)
        succcap = np.empty(64, dtype=np.int8)
        seen2 = np.empty(64, dtype=np.int64)
        cnt = evCnt[tid]
        if turn == WOLF:
            n = _preds_sheep_turn(W, S, predW, predS, NEIGH)
            m = 0
            for j in range(n):
                P = _encode_c(predW[j], predS[j], SHEEP, PLACEOFF_C, C22K,
                              CTAB_FLAT, FREELIST, WDEN, MIRROR_WR, MIRROR_CELL)
                dup = False
                for u in range(m):
                    if seen[u] == P:
                        dup = True
                        break
                if dup:
                    continue
                seen[m] = P
                m += 1
                if v == WOLF_WIN:
                    # 递减事件:羊回合 P 的"全称狼胜"计数器
                    evP[tid, cnt] = P
                    evW[tid, cnt] = predW[j]
                    evS[tid, cnt] = predS[j]
                    evNd[tid, cnt] = nd
                    evCls[tid, cnt] = WOLF_WIN
                    evAssign[tid, cnt] = 0
                    if (tab[P] >> 2) == 63:
                        evN2[tid, cnt] = _sheep_uniq_count(
                            predW[j], predS[j], PLACEOFF_C, C22K, CTAB_FLAT,
                            FREELIST, WDEN, MIRROR_WR, MIRROR_CELL, NEIGH,
                            succS, seen2)
                    else:
                        evN2[tid, cnt] = 0
                    cnt += 1
                else:
                    evP[tid, cnt] = P
                    evNd[tid, cnt] = nd
                    evCls[tid, cnt] = SHEEP_WIN
                    evAssign[tid, cnt] = 1
                    cnt += 1
        else:
            n = _preds_wolf_turn(W, S, predW, predS, NEIGH, kmax)
            m = 0
            for j in range(n):
                P = _encode_c(predW[j], predS[j], WOLF, PLACEOFF_C, C22K,
                              CTAB_FLAT, FREELIST, WDEN, MIRROR_WR, MIRROR_CELL)
                dup = False
                for u in range(m):
                    if seen[u] == P:
                        dup = True
                        break
                if dup:
                    continue
                seen[m] = P
                m += 1
                if v == SHEEP_WIN:
                    # 递减事件:狼回合 P 的"全称羊胜"计数器
                    evP[tid, cnt] = P
                    evW[tid, cnt] = predW[j]
                    evS[tid, cnt] = predS[j]
                    evNd[tid, cnt] = nd
                    evCls[tid, cnt] = SHEEP_WIN
                    evAssign[tid, cnt] = 0
                    if (tab[P] >> 2) == 63:
                        kp = 0
                        xx = predS[j]
                        while xx:
                            xx = xx & (xx - 1)
                            kp += 1
                        evN2[tid, cnt] = _wolf_uniq_count(
                            predW[j], predS[j], kp, PLACEOFF_C, C22K, CTAB_FLAT,
                            FREELIST, WDEN, MIRROR_WR, MIRROR_CELL, NEIGH,
                            succW, succS, succcap, seen2)
                    else:
                        evN2[tid, cnt] = 0
                    cnt += 1
                else:
                    evP[tid, cnt] = P
                    evNd[tid, cnt] = nd
                    evCls[tid, cnt] = WOLF_WIN
                    evAssign[tid, cnt] = 1
                    cnt += 1
        evCnt[tid] = cnt


@njit(cache=True)
def _apply_events(tab, dist, queue, tail, evP, evW, evS, evN2, evNd, evCls,
                  evAssign, evCnt, nthreads, PLACEOFF_C, C22K, WOLF_MASKS,
                  WR_OF_DENSE, FREECELLS, FREELIST, CTAB_FLAT, WDEN, MIRROR_WR,
                  MIRROR_CELL, NEIGH, succW, succS, succcap, seen2):
    for tid in range(nthreads):
        for j in range(evCnt[tid]):
            P = evP[tid, j]
            bP = tab[P]
            if (bP & 3) != 0:
                continue
            if evAssign[tid, j] == 1:
                tab[P] = evCls[tid, j]
                dist[P] = evNd[tid, j]
                queue[tail] = P
                tail += 1
            else:
                c = bP >> 2
                if c == 63:
                    n2 = evN2[tid, j]
                    if n2 == 0:
                        # 兜底(正常不会发生):串行重算
                        Wp = evW[tid, j]
                        Sp = evS[tid, j]
                        kp = 0
                        xx = Sp
                        while xx:
                            xx = xx & (xx - 1)
                            kp += 1
                        if evCls[tid, j] == WOLF_WIN:
                            n2 = _sheep_uniq_count(Wp, Sp, PLACEOFF_C, C22K,
                                                   CTAB_FLAT, FREELIST, WDEN,
                                                   MIRROR_WR, MIRROR_CELL, NEIGH,
                                                   succS, seen2)
                        else:
                            n2 = _wolf_uniq_count(Wp, Sp, kp, PLACEOFF_C, C22K,
                                                  CTAB_FLAT, FREELIST, WDEN,
                                                  MIRROR_WR, MIRROR_CELL, NEIGH,
                                                  succW, succS, succcap, seen2)
                    if n2 <= 1:
                        tab[P] = evCls[tid, j]
                        dist[P] = evNd[tid, j]
                        queue[tail] = P
                        tail += 1
                    else:
                        tab[P] = ((n2 - 1) << 2)
                else:
                    c -= 1
                    if c == 0:
                        tab[P] = evCls[tid, j]
                        dist[P] = evNd[tid, j]
                        queue[tail] = P
                        tail += 1
                    else:
                        tab[P] = (c << 2)
    return tail


def solve_par(kmax=15, outdir=None, resume=False, checkpoint_s=1800,
              verify=True, chunk=200_000):
    """并行破解。存档格式与 endgame_full.solve_full 完全兼容,可互换续跑。"""
    if outdir is None:
        outdir = default_outdir()
    os.makedirs(outdir, exist_ok=True)
    N = full_size(kmax)
    tab_path = os.path.join(outdir, "full_packed.npy")
    queue_path = os.path.join(outdir, "full_queue.dat")
    dist_path = os.path.join(outdir, "full_dist.dat")
    meta_path = os.path.join(outdir, "full_meta.npy")

    nthreads = get_num_threads()
    print(f"[并行] 线程数={nthreads}", flush=True)

    if resume:
        if not ((os.path.exists(tab_path) or os.path.exists(tab_path + ".prev"))
                and os.path.exists(meta_path)):
            raise RuntimeError("resume 模式找不到可用存档,已拒绝重新开始(防止误删队列)")
        used, head, tail = _load_checkpoint_pair(tab_path, meta_path)
        t0 = time.time()
        tab = np.load(used)
        queue = np.memmap(queue_path, dtype=np.uint64, mode="r+", shape=(N,))
        dist = np.memmap(dist_path, dtype=np.uint16, mode="r+", shape=(N,))
        print(f"[并行续跑] 存档={os.path.basename(used)} 头={head:,} 尾={tail:,} "
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
        print(f"[并行种子] 入队={tail:,}  用时={time.time()-t0:.1f}s", flush=True)

    # 事件缓冲区:每线程一行,容量按块大小×每状态最多60前驱+余量
    cap = max((chunk // nthreads + 2) * 64, 1 << 20)
    evP = np.zeros((nthreads, cap), dtype=np.int64)
    evW = np.zeros((nthreads, cap), dtype=np.int64)
    evS = np.zeros((nthreads, cap), dtype=np.int64)
    evN2 = np.zeros((nthreads, cap), dtype=np.int16)
    evNd = np.zeros((nthreads, cap), dtype=np.int16)
    evCls = np.zeros((nthreads, cap), dtype=np.int8)
    evAssign = np.zeros((nthreads, cap), dtype=np.int8)
    evCnt = np.zeros(nthreads, dtype=np.int64)
    succW = np.empty(64, dtype=np.int64)
    succS = np.empty(64, dtype=np.int64)
    succcap = np.empty(64, dtype=np.int8)
    seen2 = np.empty(64, dtype=np.int64)

    t0 = time.time()
    last = t0
    processed_total = 0
    while head < tail:
        c = min(chunk, tail - head)
        evCnt[:] = 0
        _par_pop_chunk(kmax, tab, dist, queue, head, c, evP, evW, evS, evN2,
                       evNd, evCls, evAssign, evCnt, PLACEOFF_C, C22K, WOLF_MASKS,
                       WR_OF_DENSE, FREECELLS, FREELIST, CTAB_FLAT, WDEN,
                       MIRROR_WR, MIRROR_CELL, NEIGH)
        head += c
        if int(evCnt.max()) >= cap:
            raise RuntimeError(f"事件缓冲区溢出: {int(evCnt.max())} >= {cap}")
        tail = _apply_events(tab, dist, queue, tail, evP, evW, evS, evN2, evNd,
                             evCls, evAssign, evCnt, nthreads, PLACEOFF_C, C22K,
                             WOLF_MASKS, WR_OF_DENSE, FREECELLS, FREELIST,
                             CTAB_FLAT, WDEN, MIRROR_WR, MIRROR_CELL, NEIGH,
                             succW, succS, succcap, seen2)
        processed_total += c
        now = time.time()
        if now - last >= checkpoint_s or head >= tail:
            last = now
            _checkpoint(tab, head, tail, tab_path, meta_path, queue, dist)
            rate = processed_total / max(1e-9, now - t0)
            eta_h = (tail - head) / max(1e-9, rate) / 3600
            print(f"  [并行进度] 已处理={processed_total:,} 剩余={tail-head:,} "
                  f"速率={rate:,.0f}/s 预计剩余={eta_h:.1f}h", flush=True)

    t2 = time.time()
    nw, ns, nd = _finalize(tab, N)
    counts = (nw, ns, nd)
    _checkpoint(tab, head, tail, tab_path, meta_path, queue, dist)
    print(f"并行求解完成: 狼胜={counts[0]:,} 羊胜={counts[1]:,} 和={counts[2]:,} "
          f"传播用时={(t2-t0)/3600:.2f}h", flush=True)
    bad = None
    if verify:
        print("开始独立复核...", flush=True)
        t3 = time.time()
        bad = _verify_full(kmax, N, tab, PLACEOFF_C, C22K, WOLF_MASKS,
                           WR_OF_DENSE, FREECELLS, FREELIST, CTAB_FLAT, WDEN,
                           MIRROR_WR, MIRROR_CELL, NEIGH)
        print(f"复核完成: 错误={bad}  用时={(time.time()-t3)/60:.1f}min", flush=True)
    if bad is None or bad == 0:
        with open(os.path.join(outdir, "full_done.flag"), "w") as f:
            f.write("done\n")
    return dict(N=N, wolf=counts[0], sheep=counts[1], draw=counts[2],
                solve_h=(t2 - t0) / 3600, bad=bad)


if __name__ == "__main__":
    import sys
    km = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    resume = "--resume" in sys.argv
    outdir = None
    for a in sys.argv:
        if a.startswith("--outdir="):
            outdir = a.split("=", 1)[1]
    solve_par(km, outdir=outdir, resume=resume)

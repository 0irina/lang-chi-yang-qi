# -*- coding: utf-8 -*-
"""狼吃羊棋 逆行求解器(Numba)——全局索引空间(k=3..15 羊数层合并求解)

原理(与 Gasser 破解九子棋同法):
  终局种子入队 → 逆向传播:
    * 狼胜:狼方节点只要有一手后继是"狼胜"即狼胜(存在量词);
            羊方节点需所有后继都是"狼胜"才是狼胜(全称量词,用计数器)。
    * 羊胜:对称(羊方存在,狼方全称)。
  队列耗尽后仍未定的局面 = 和棋(等价于"三重复判和"的完美对局语义)。

重要:逆向传播会跨羊数层——第 k 层局面的前驱可能在第 k+1 层(吃子被反推),
因此所有层必须放入同一个索引空间一起求不动点。全局摆法索引:
    p = PLACEOFF[ki] + wolf_rank * C22K[ki] + sheep_rank,  ki = 羊数-3
    状态索引 = p * 2 + turn
"""
import os
import sys
import time

import numpy as np
try:
    from numba import njit
except ImportError:
    # 运行时(打包版)不需要求解器:numba 缺失时退化为普通函数,查表功能不受影响
    def njit(*args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda f: f

import rules
from rules import WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, ONGOING, ALL_MASK
from index import (WOLF_MASKS, FREECELLS, FREELIST, CTAB_FLAT, C,
                   N_FREE, N_CELLS, N_WOLF_COMB,
                   K_MIN, K_MAX, C22K, PLACEOFF)

# 邻接表 int8[25,4],-1 表示越界
_NEIGH = np.full((25, 4), -1, dtype=np.int8)
for p in range(25):
    for i, q in enumerate(rules.NEIGH[p]):
        _NEIGH[p, i] = q
NEIGH = _NEIGH

# ---------------- 基础位运算 ----------------
@njit(cache=True, inline='always')
def _lsb_pos(x):
    """x 为 2 的幂,返回其位位置"""
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
    """狼的后继。Wout/Sout/capout 容量 >= 24。返回个数。"""
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


# ---------------- 全局编解码 ----------------
@njit(cache=True)
def _encode(W, S, turn, PLACEOFF, C22K, CTAB_FLAT, FREELIST):
    k = _pc(S)
    ki = k - 3
    wr = 0
    t = 1
    x = W
    while x:
        lsb = x & -x
        p = _lsb_pos(lsb)
        x = x ^ lsb
        wr += CTAB_FLAT[p * 16 + t]
        t += 1
    sr = 0
    t = 1
    x = S
    while x:
        lsb = x & -x
        p = _lsb_pos(lsb)
        x = x ^ lsb
        j = FREELIST[wr, p]
        sr += CTAB_FLAT[j * 16 + t]
        t += 1
    return (PLACEOFF[ki] + wr * C22K[ki] + sr) * 2 + turn


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
def _decode(idx, PLACEOFF, C22K, WOLF_MASKS, FREECELLS, CTAB_FLAT):
    turn = idx & 1
    p = idx >> 1
    # 找所属羊数层(从高往低扫)
    ki = 12
    while ki > 0 and p < PLACEOFF[ki]:
        ki -= 1
    k = ki + 3
    t = p - PLACEOFF[ki]
    sr = t % C22K[ki]
    wr = t // C22K[ki]
    W = WOLF_MASKS[wr]
    S = _unrank_sheep(wr, sr, k, FREECELLS, CTAB_FLAT)
    return W, S, turn, k


# ---------------- 前驱生成(逆向传播用) ----------------
@njit(cache=True)
def _preds_sheep_turn(W, S, Wout, Sout, NEIGH):
    """当前为狼回合;前驱 = 羊刚走一步的局面(羊回合,同层)"""
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
    """当前为羊回合;前驱 = 狼刚走完的局面(狼回合,单步同层或吃子来自上一层)。
    逆吃子会使羊数 +1,若已达 kmax 则不再生成(超出表空间的局面不在本表考虑范围,
    且表内局面的正向后继都不超过 kmax,定点解自洽)。"""
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
        # 逆单步:狼从空邻居 p 走到 q(同层)
        for i in range(4):
            p = NEIGH[q, i]
            if p >= 0 and ((empty >> p) & 1):
                Wout[n] = (W ^ lsb) | (1 << p)
                Sout[n] = S
                n += 1
        # 逆吃子:狼从 p 跳过空格 mid 落到 q 吃掉 q 上的羊 → 前驱有 k+1 只羊
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


# ---------------- 计数器惰性初始化 ----------------
@njit(cache=True)
def _init_sheep_counter(idx, value, PLACEOFF, C22K, WOLF_MASKS, FREECELLS,
                        CTAB_FLAT, FREELIST, NEIGH, Sout):
    """羊回合节点:返回羊后继总数(计数器初始化用)"""
    W, S, turn, k = _decode(idx, PLACEOFF, C22K, WOLF_MASKS, FREECELLS, CTAB_FLAT)
    n = _sheep_succs(W, S, Sout, NEIGH)
    return n


@njit(cache=True)
def _init_wolf_counter(idx, value, PLACEOFF, C22K, WOLF_MASKS, FREECELLS,
                       CTAB_FLAT, FREELIST, NEIGH, Wout, Sout, capout):
    """狼回合节点:返回狼后继总数(含吃子;计数器初始化用)"""
    W, S, turn, k = _decode(idx, PLACEOFF, C22K, WOLF_MASKS, FREECELLS, CTAB_FLAT)
    n = _wolf_succs(W, S, Wout, Sout, capout, NEIGH)
    return n


@njit(cache=True)
def _wolf_has_winning_capture(W, S, k, value, PLACEOFF, C22K, CTAB_FLAT, FREELIST,
                              NEIGH, Wout, Sout, capout):
    """狼回合节点是否存在必胜吃子:k>=4 时吃入 k=3 终局(种子狼胜)即胜。
    k==3 分支为防御性代码(新规则下 k=3 双方回合已在种子阶段定为狼胜)。"""
    n = _wolf_succs(W, S, Wout, Sout, capout, NEIGH)
    for i in range(n):
        if capout[i]:
            if k == 3:
                return True
            j = _encode(Wout[i], Sout[i], SHEEP, PLACEOFF, C22K, CTAB_FLAT, FREELIST)
            if value[j] == WOLF_WIN:
                return True
    return False


# ---------------- 全局空间求解 ----------------
@njit(cache=True)
def _solve_space(kmax, N, value_out, dist_out, PLACEOFF, C22K, WOLF_MASKS,
                 FREECELLS, FREELIST, CTAB_FLAT, NEIGH):
    value = np.zeros(N, dtype=np.uint8)
    counter = np.full(N, 255, dtype=np.uint8)  # 255 = 未初始化
    dist = np.zeros(N, dtype=np.uint8)         # 到终局距离(BFS 波数,饱和 255)
    queue = np.empty(N, dtype=np.int64)
    tail = 0
    head = 0

    predW = np.empty(64, dtype=np.int64)
    predS = np.empty(64, dtype=np.int64)
    initW = np.empty(64, dtype=np.int64)
    initS = np.empty(64, dtype=np.int64)
    initcap = np.empty(64, dtype=np.int8)
    succS = np.empty(64, dtype=np.int64)
    capW = np.empty(64, dtype=np.int64)
    capS = np.empty(64, dtype=np.int64)
    capc = np.empty(64, dtype=np.int8)

    # ---- 终局种子 ----
    for ki in range(kmax - 3 + 1):
        k = ki + 3
        C22k = C22K[ki]
        base = PLACEOFF[ki]
        for wr in range(N_WOLF_COMB):
            W = WOLF_MASKS[wr]
            for sr in range(C22k):
                S = _unrank_sheep(wr, sr, k, FREECELLS, CTAB_FLAT)
                idx = (base + wr * C22k + sr) * 2
                if k == 3:
                    # 新规则:羊剩3只=狼胜,双方回合均终局
                    value[idx] = WOLF_WIN
                    queue[tail] = idx
                    tail += 1
                    value[idx + 1] = WOLF_WIN
                    queue[tail] = idx + 1
                    tail += 1
                else:
                    # 狼回合
                    if not _has_wolf_move(W, S, NEIGH):
                        value[idx] = SHEEP_WIN
                        queue[tail] = idx
                        tail += 1
                    elif _wolf_has_winning_capture(W, S, k, value, PLACEOFF,
                                                   C22K, CTAB_FLAT, FREELIST,
                                                   NEIGH, capW, capS, capc):
                        value[idx] = WOLF_WIN
                        queue[tail] = idx
                        tail += 1
                    # 羊回合
                    if not _has_sheep_move(W, S, NEIGH):
                        value[idx + 1] = WOLF_WIN
                        queue[tail] = idx + 1
                        tail += 1

    # ---- 逆向传播 ----
    while head < tail:
        X = queue[head]
        head += 1
        v = value[X]
        turn = X & 1
        dX = dist[X]
        nd = dX + 1
        if nd > 255:
            nd = 255
        W, S, t, k = _decode(X, PLACEOFF, C22K, WOLF_MASKS, FREECELLS, CTAB_FLAT)
        if turn == WOLF:
            # 前驱是羊回合
            n = _preds_sheep_turn(W, S, predW, predS, NEIGH)
            for i in range(n):
                P = _encode(predW[i], predS[i], SHEEP, PLACEOFF, C22K, CTAB_FLAT, FREELIST)
                if value[P] != 0:
                    continue
                if v == WOLF_WIN:
                    # 羊回合需所有后继皆狼胜 → 计数器
                    if counter[P] == 255:
                        # 首次触发:总数 - 1(X 已确认;其余后继弹出时若为狼胜再减)
                        n = _init_sheep_counter(P, value, PLACEOFF, C22K,
                                                WOLF_MASKS, FREECELLS, CTAB_FLAT,
                                                FREELIST, NEIGH, succS)
                        if n <= 1:
                            # X 是唯一后继 → 已确定狼胜
                            value[P] = WOLF_WIN
                            dist[P] = nd
                            queue[tail] = P
                            tail += 1
                            continue
                        counter[P] = n - 1
                    else:
                        counter[P] -= 1
                        if counter[P] == 0:
                            value[P] = WOLF_WIN
                            dist[P] = nd
                            queue[tail] = P
                            tail += 1
                else:
                    # 羊有一手走到羊胜 → 羊胜
                    value[P] = SHEEP_WIN
                    dist[P] = nd
                    queue[tail] = P
                    tail += 1
        else:
            # 前驱是狼回合
            n = _preds_wolf_turn(W, S, predW, predS, NEIGH, kmax)
            for i in range(n):
                P = _encode(predW[i], predS[i], WOLF, PLACEOFF, C22K, CTAB_FLAT, FREELIST)
                if value[P] != 0:
                    continue
                if v == SHEEP_WIN:
                    # 狼回合需所有后继皆羊胜 → 计数器
                    if counter[P] == 255:
                        # 首次触发:总数 - 1(X 已确认;其余后继弹出时若为羊胜再减)
                        n = _init_wolf_counter(P, value, PLACEOFF, C22K,
                                               WOLF_MASKS, FREECELLS, CTAB_FLAT,
                                               FREELIST, NEIGH, initW, initS, initcap)
                        if n <= 1:
                            # X 是唯一后继 → 已确定羊胜
                            value[P] = SHEEP_WIN
                            dist[P] = nd
                            queue[tail] = P
                            tail += 1
                            continue
                        counter[P] = n - 1
                    else:
                        counter[P] -= 1
                        if counter[P] == 0:
                            value[P] = SHEEP_WIN
                            dist[P] = nd
                            queue[tail] = P
                            tail += 1
                else:
                    # 狼有一手走到狼胜 → 狼胜
                    value[P] = WOLF_WIN
                    dist[P] = nd
                    queue[tail] = P
                    tail += 1

    # 未定 = 和棋
    for i in range(N):
        if value[i] == 0:
            value[i] = DRAW
    value_out[:] = value
    dist_out[:] = dist
    return tail


# ---------------- 独立复核(从后继重新推导,查 bug 用) ----------------
@njit(cache=True)
def _verify_space(kmax, N, value, PLACEOFF, C22K, WOLF_MASKS, FREECELLS,
                  FREELIST, CTAB_FLAT, NEIGH):
    bad = 0
    Wout = np.empty(64, dtype=np.int64)
    Sout = np.empty(64, dtype=np.int64)
    capout = np.empty(64, dtype=np.int8)
    for ki in range(kmax - 3 + 1):
        k = ki + 3
        C22k = C22K[ki]
        base = PLACEOFF[ki]
        for wr in range(N_WOLF_COMB):
            W = WOLF_MASKS[wr]
            for sr in range(C22k):
                S = _unrank_sheep(wr, sr, k, FREECELLS, CTAB_FLAT)
                idx = (base + wr * C22k + sr) * 2
                if k == 3:
                    # 新规则:羊剩3只=狼胜,双方回合均终局
                    if value[idx] != WOLF_WIN:
                        bad += 1
                    if value[idx + 1] != WOLF_WIN:
                        bad += 1
                    continue
                # 狼回合
                n = _wolf_succs(W, S, Wout, Sout, capout, NEIGH)
                if n == 0:
                    exp = SHEEP_WIN
                else:
                    has_win = False
                    all_lose = True
                    for i in range(n):
                        # 新规则:吃子落到 k=3 终局,其种子值=狼胜,查表即可
                        sv = value[_encode(Wout[i], Sout[i], SHEEP, PLACEOFF,
                                           C22K, CTAB_FLAT, FREELIST)]
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
                if value[idx] != exp:
                    bad += 1
                # 羊回合
                n2 = _sheep_succs(W, S, Sout, NEIGH)
                if n2 == 0:
                    exp2 = WOLF_WIN
                else:
                    has_win = False
                    all_lose = True
                    for i in range(n2):
                        sv = value[_encode(W, Sout[i], WOLF, PLACEOFF, C22K,
                                           CTAB_FLAT, FREELIST)]
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
                if value[idx + 1] != exp2:
                    bad += 1
    return bad


# ---------------- 驱动 ----------------
def default_outdir():
    if getattr(sys, "frozen", False):
        # PyInstaller 打包版:数据表放在 exe 同级的 tt\ 目录
        return os.path.join(os.path.dirname(sys.executable), "tt")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "tt")


def space_size(kmax):
    """k=3..kmax 合并空间的状态数(含两个回合)"""
    ki = kmax - 3
    placements = int(PLACEOFF[ki]) + N_WOLF_COMB * int(C22K[ki])
    return placements * 2


def build(kmax=5, outdir=None):
    if outdir is None:
        outdir = default_outdir()
    os.makedirs(outdir, exist_ok=True)
    N = space_size(kmax)
    t0 = time.time()
    value = np.empty(N, dtype=np.uint8)
    dist = np.empty(N, dtype=np.uint8)
    tail = _solve_space(kmax, N, value, dist, PLACEOFF, C22K, WOLF_MASKS,
                        FREECELLS, FREELIST, CTAB_FLAT, NEIGH)
    t1 = time.time()
    bad = _verify_space(kmax, N, value, PLACEOFF, C22K, WOLF_MASKS, FREECELLS,
                        FREELIST, CTAB_FLAT, NEIGH)
    t2 = time.time()
    counts = (int((value == WOLF_WIN).sum()),
              int((value == SHEEP_WIN).sum()),
              int((value == DRAW).sum()))
    fname = os.path.join(outdir, f"tt_3_{kmax}.npy")
    np.save(fname, value)
    np.save(os.path.join(outdir, f"dist_3_{kmax}.npy"), dist)
    print(f"k=3..{kmax}  N={N:,}  狼胜={counts[0]:,}  羊胜={counts[1]:,}  和={counts[2]:,}  "
          f"入队={tail:,}  求解={t1-t0:.1f}s  复核={t2-t1:.1f}s  错误={bad}")
    return dict(N=N, enqueued=int(tail), wolf=counts[0], sheep=counts[1],
                draw=counts[2], solve_s=t1 - t0, verify_s=t2 - t1, bad=bad)


# ---------------- 查询 ----------------
_TABLE = None
_DIST = None
_KM = 0
_LOAD_DIR = None
_FULL = None          # 全破解表(镜像压缩,2bit/6bit 打包)
_FULL_DIST = None


def load_tables(outdir=None, upto=None):
    """加载已解出的残局表(mmap,只读)。仅当存在 full_done.flag 时才使用全破解表
    (破解过程中的检查点文件 full_packed.npy 是不完整的,不能用于查询)。"""
    global _TABLE, _DIST, _KM, _LOAD_DIR, _FULL, _FULL_DIST
    if outdir is None:
        outdir = default_outdir()
    _LOAD_DIR = outdir
    _FULL = None
    _FULL_DIST = None
    full_path = os.path.join(outdir, "full_packed.npy")
    done_flag = os.path.join(outdir, "full_done.flag")
    if os.path.exists(full_path) and os.path.exists(done_flag):
        _FULL = np.load(full_path, mmap_mode="r")
        df = os.path.join(outdir, "full_dist.dat")
        if os.path.exists(df):
            _FULL_DIST = np.memmap(df, dtype=np.uint16, mode="r",
                                   shape=(len(_FULL),))
        _KM = 15
        _TABLE = None
        _DIST = None
        return [15]
    cand = []
    for fname in sorted(os.listdir(outdir)):
        if fname.startswith("tt_3_") and fname.endswith(".npy"):
            km = int(fname.split("_")[-1].split(".")[0])
            if upto is not None and km > upto:
                continue
            cand.append(km)
    if not cand:
        _TABLE = None
        _DIST = None
        _KM = 0
        return []
    kmax = max(cand)
    _TABLE = np.load(os.path.join(outdir, f"tt_3_{kmax}.npy"), mmap_mode="r")
    df = os.path.join(outdir, f"dist_3_{kmax}.npy")
    if os.path.exists(df):
        _DIST = np.load(df, mmap_mode="r")
    else:
        _DIST = None
    _KM = kmax
    return [kmax]


def _canon_idx(wolves: int, sheep: int, turn: int) -> int:
    from index import (canon_state, rank_sheep_mask, C22K, PLACEOFF_C, WDEN)
    cwr, cs = canon_state(wolves, sheep)
    k = sheep.bit_count()
    sr = rank_sheep_mask(cwr, cs)
    ki = k - 3
    return (int(PLACEOFF_C[ki]) + int(WDEN[cwr]) * int(C22K[ki]) + sr) * 2 + turn


def lookup(wolves: int, sheep: int, turn: int) -> int:
    """查询局面胜负。羊 <=3 直接狼胜;超出已解层返回 ONGOING。"""
    k = rules.popcount(sheep)
    if k <= 3:
        return WOLF_WIN
    if _FULL is not None:
        if k > 15:
            return ONGOING
        return int(_FULL[_canon_idx(wolves, sheep, turn)] & 3)
    if _TABLE is None or k > _KM:
        return ONGOING
    from index import rank_wolf_mask, rank_sheep_mask
    wr = rank_wolf_mask(wolves)
    sr = rank_sheep_mask(wr, sheep)
    ki = k - 3
    idx = (int(PLACEOFF[ki]) + wr * int(C22K[ki]) + sr) * 2 + turn
    return int(_TABLE[idx])


def lookup_dist(wolves: int, sheep: int, turn: int) -> int:
    """查询到终局距离(完美双方下)。未解层返回 -1。"""
    k = rules.popcount(sheep)
    if k <= 3:
        return 0
    if _FULL is not None:
        if _FULL_DIST is None or k > 15:
            return -1
        return int(_FULL_DIST[_canon_idx(wolves, sheep, turn)])
    if _TABLE is None or k > _KM or _DIST is None:
        return -1
    from index import rank_wolf_mask, rank_sheep_mask
    wr = rank_wolf_mask(wolves)
    sr = rank_sheep_mask(wr, sheep)
    ki = k - 3
    idx = (int(PLACEOFF[ki]) + wr * int(C22K[ki]) + sr) * 2 + turn
    return int(_DIST[idx])


if __name__ == "__main__":
    import sys
    mk = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    build(mk)

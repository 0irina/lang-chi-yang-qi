# -*- coding: utf-8 -*-
"""局面 <-> 组合索引 编解码

状态空间:3 狼摆法 C(25,3)=2300,羊占剩余 22 格中的 k 格(k=3..15)。
狼位索引用 25 选 3 的组合数系统;羊位索引用"剩余 22 格"上的组合数系统
(剩余格列表由狼摆法决定,按升序编号 0..21)。

分层(按羊数 k)索引:layer_idx = (wolf_rank * C(22,k) + sheep_rank) * 2 + turn
全局索引:global_idx = (SHEEP_OFFSETS[k] + wolf_rank * C(22,k) + sheep_rank) * 2 + turn
"""
import numpy as np

N_CELLS = 25
N_FREE = 22
MIN_SHEEP = 3
MAX_SHEEP = 15
N_WOLF_COMB = 2300  # C(25,3)


def build_ctab():
    # 行数要覆盖 n=25:unrank 狼时需用 C(25,3)=2300 作为上界哨兵
    C = np.zeros((N_CELLS + 1, 16), dtype=np.int64)
    for n in range(N_CELLS + 1):
        C[n, 0] = 1
        for k in range(1, 16):
            if k > n:
                break
            C[n, k] = C[n - 1, k - 1] + C[n - 1, k]
    return C


CTAB = build_ctab()                                   # (25, 16)
CTAB_FLAT = np.ascontiguousarray(CTAB.ravel())        # int64[400], 行主序, stride 16


def C(n: int, k: int) -> int:
    return int(CTAB[n, k])


SHEEP_OFFSETS = {}
_off = 0
for _k in range(MIN_SHEEP, MAX_SHEEP + 1):
    SHEEP_OFFSETS[_k] = _off
    _off += C(N_FREE, _k)
TOTAL_PLACEMENTS = _off  # 4,083,994

# 供全局索引(跨羊数层)使用的数组
K_MIN = 3
K_MAX = 15
C22K = np.array([C(N_FREE, k) for k in range(K_MIN, K_MAX + 1)], dtype=np.int64)
SHEEP_OFF = np.array([SHEEP_OFFSETS[k] for k in range(K_MIN, K_MAX + 1)], dtype=np.int64)
PLACEOFF = SHEEP_OFF * N_WOLF_COMB  # 第 k 层前的摆法总数(不含回合)


def rank_wolf_mask(mask: int) -> int:
    """3 子集在 25 格上的组合排名"""
    r = 0
    i = 1
    x = mask
    while x:
        lsb = x & -x
        p = lsb.bit_length() - 1
        x ^= lsb
        r += C(p, i)
        i += 1
    return r


def unrank_wolf_mask(rank: int) -> int:
    x = 0
    r = rank
    for j in (3, 2, 1):
        p = 0
        while C(p, j) <= r:
            p += 1
        p -= 1
        r -= C(p, j)
        x |= 1 << p
    return x


def build_wolf_tables():
    masks = np.empty(N_WOLF_COMB, dtype=np.int32)
    for r in range(N_WOLF_COMB):
        masks[r] = unrank_wolf_mask(r)
    free_cells = np.zeros((N_WOLF_COMB, N_FREE), dtype=np.int8)
    free_list = np.full((N_WOLF_COMB, N_CELLS), -1, dtype=np.int8)
    for r in range(N_WOLF_COMB):
        m = int(masks[r])
        j = 0
        for p in range(N_CELLS):
            if not ((m >> p) & 1):
                free_cells[r, j] = p
                free_list[r, p] = j
                j += 1
    return masks, free_cells, free_list


WOLF_MASKS, FREECELLS, FREELIST = build_wolf_tables()
# WOLF_MASKS[r]      : 第 r 号狼摆法的位棋盘 (int32[2300])
# FREECELLS[r, j]    : 第 r 号狼摆法下第 j 个空格的棋盘位置 (int8[2300,22])
# FREELIST[r, cell]  : 棋盘位置在剩余格列表中的编号,非空格为 -1 (int8[2300,25])


def rank_sheep_mask(wolf_rank: int, sheep_mask: int) -> int:
    """羊位在"该狼摆法的 22 个剩余格"上的组合排名"""
    r = 0
    i = 1
    x = sheep_mask
    while x:
        lsb = x & -x
        p = lsb.bit_length() - 1
        x ^= lsb
        j = int(FREELIST[wolf_rank, p])
        if j < 0:
            raise ValueError("羊落在了狼格上")
        r += C(j, i)
        i += 1
    return r


def unrank_sheep_mask(wolf_rank: int, rank: int, k: int) -> int:
    x = 0
    r = rank
    for j in range(k, 0, -1):
        p = 0
        while C(p, j) <= r:
            p += 1
        p -= 1
        r -= C(p, j)
        x |= 1 << int(FREECELLS[wolf_rank, p])
    return x


def layer_index(wolf_rank: int, sheep_rank: int, turn: int, k: int) -> int:
    return (wolf_rank * C(N_FREE, k) + sheep_rank) * 2 + turn


def global_index(wolves: int, sheep: int, turn: int) -> int:
    k = sheep.bit_count()
    wr = rank_wolf_mask(wolves)
    sr = rank_sheep_mask(wr, sheep)
    off = SHEEP_OFFSETS[k] + wr * C(N_FREE, k)
    return (off + sr) * 2 + turn


# ---------------- 镜像压缩(左右对称) ----------------
def _mirror_mask(m: int) -> int:
    r = 0
    x = m
    while x:
        lsb = x & -x
        p = lsb.bit_length() - 1
        x ^= lsb
        r |= 1 << (p // 5 * 5 + (4 - p % 5))
    return r


MIRROR_CELL = np.array([p // 5 * 5 + (4 - p % 5) for p in range(N_CELLS)], dtype=np.int8)


def build_mirror_tables():
    MIRROR_WR = np.empty(N_WOLF_COMB, dtype=np.int16)
    for wr in range(N_WOLF_COMB):
        MIRROR_WR[wr] = rank_wolf_mask(_mirror_mask(int(WOLF_MASKS[wr])))
    # 规范狼排位:wr <= wrm 者保留,并把 wrm 映射到 wr 的紧凑编号
    WDEN = np.empty(N_WOLF_COMB, dtype=np.int16)
    dense_of = {}
    m = 0
    for wr in range(N_WOLF_COMB):
        wrm = int(MIRROR_WR[wr])
        if wr <= wrm:
            dense_of[wr] = m
            m += 1
    for wr in range(N_WOLF_COMB):
        wrm = int(MIRROR_WR[wr])
        WDEN[wr] = dense_of[wr] if wr <= wrm else dense_of[wrm]
    WR_OF_DENSE = np.empty(m, dtype=np.int16)
    for wr, d in dense_of.items():
        WR_OF_DENSE[d] = wr
    return MIRROR_WR, WDEN, WR_OF_DENSE


MIRROR_WR, WDEN, WR_OF_DENSE = build_mirror_tables()
M_CANON = len(WR_OF_DENSE)  # 规范狼摆法数(~1175)
PLACEOFF_C = SHEEP_OFF * M_CANON  # 规范空间的分层摆法偏移


def canon_state(wolves: int, sheep: int):
    """返回规范摆法 (cwr, canon_sheep_mask):狼位取镜像较小者;狼形自身对称时
    羊位取镜像 rank 较小者。"""
    wr = rank_wolf_mask(wolves)
    wrm = int(MIRROR_WR[wr])
    if wr < wrm:
        return wr, sheep
    if wr > wrm:
        return wrm, _mirror_mask(sheep)
    sm = _mirror_mask(sheep)
    if rank_sheep_mask(wr, sm) < rank_sheep_mask(wr, sheep):
        return wr, sm
    return wr, sheep

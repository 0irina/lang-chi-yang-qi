# -*- coding: utf-8 -*-
"""狼吃羊棋 权威规则(纯 Python 位棋盘版)

棋盘 5x5,位置编号 0..24(pos = row*5 + col)。
- 狼 3 只,初始第 1 行中间三列(1-based:(1,2),(1,3),(1,4)),即 bits 1,2,3
- 羊 15 只,初始第 3~5 行排满,即 bits 10..24
- 狼先手,双方轮流,每回合动一个棋子,上下左右走一格
- 吃子:狼与羊在同一直线且中间恰好隔 1 个空格时,狼跳 2 格落到羊的位置吃掉
- 终局判定(顺序):
  1) 羊被吃到只剩 3 只        -> 狼胜
  2) 轮到狼走且狼无任何走法    -> 羊胜
  3) 轮到羊走且羊无任何走法    -> 狼胜(用户确认)
- 循环局面 -> 和棋(实际对弈中按"重复局面回避"处理,见 engine)
"""
from __future__ import annotations

WOLF = 0
SHEEP = 1

WOLF_WIN = 1   # 狼胜
SHEEP_WIN = 2  # 羊胜
DRAW = 3       # 和棋
ONGOING = 0    # 未在表中/未终局

WIN_NAMES = {WOLF_WIN: "狼胜", SHEEP_WIN: "羊胜", DRAW: "和棋", ONGOING: "进行中"}

INIT_WOLVES = (1 << 1) | (1 << 2) | (1 << 3)
INIT_SHEEP = 0
for _r in range(2, 5):
    for _c in range(5):
        INIT_SHEEP |= 1 << (_r * 5 + _c)

ALL_MASK = (1 << 25) - 1


def _build_neigh():
    n = []
    for p in range(25):
        r, c = divmod(p, 5)
        lst = []
        if r > 0:
            lst.append(p - 5)
        if r < 4:
            lst.append(p + 5)
        if c > 0:
            lst.append(p - 1)
        if c < 4:
            lst.append(p + 1)
        n.append(tuple(lst))
    return tuple(n)


NEIGH = _build_neigh()


def popcount(x: int) -> int:
    return x.bit_count()


def wolf_moves(wolves: int, sheep: int):
    """狼的全部走法,返回 [(from, to, is_capture)]"""
    res = []
    empty = ~(wolves | sheep) & ALL_MASK
    w = wolves
    while w:
        lsb = w & -w
        p = lsb.bit_length() - 1
        w ^= lsb
        r, c = divmod(p, 5)
        # 单步走
        for q in NEIGH[p]:
            if (empty >> q) & 1:
                res.append((p, q, False))
        # 跳 2 格吃羊(中间 1 空格)
        if r >= 2:  # 上
            mid, tgt = p - 5, p - 10
            if (empty >> mid) & 1 and (sheep >> tgt) & 1:
                res.append((p, tgt, True))
        if r <= 2:  # 下
            mid, tgt = p + 5, p + 10
            if (empty >> mid) & 1 and (sheep >> tgt) & 1:
                res.append((p, tgt, True))
        if c >= 2:  # 左
            mid, tgt = p - 1, p - 2
            if (empty >> mid) & 1 and (sheep >> tgt) & 1:
                res.append((p, tgt, True))
        if c <= 2:  # 右
            mid, tgt = p + 1, p + 2
            if (empty >> mid) & 1 and (sheep >> tgt) & 1:
                res.append((p, tgt, True))
    return res


def sheep_moves(wolves: int, sheep: int):
    """羊的全部走法,返回 [(from, to)]"""
    res = []
    empty = ~(wolves | sheep) & ALL_MASK
    s = sheep
    while s:
        lsb = s & -s
        p = lsb.bit_length() - 1
        s ^= lsb
        for q in NEIGH[p]:
            if (empty >> q) & 1:
                res.append((p, q))
    return res


def apply_wolf_move(wolves: int, sheep: int, frm: int, to: int):
    w2 = (wolves ^ (1 << frm)) | (1 << to)
    s2 = sheep & ~(1 << to)  # 若目标有羊则吃掉
    return w2, s2


def apply_sheep_move(wolves: int, sheep: int, frm: int, to: int):
    return wolves, (sheep ^ (1 << frm)) | (1 << to)


def outcome(wolves: int, sheep: int, turn: int):
    """终局判定。返回 (是否终局, 结果)。未终局返回 (False, None)。"""
    if popcount(sheep) <= 3:
        return True, WOLF_WIN
    if turn == WOLF:
        if not wolf_moves(wolves, sheep):
            return True, SHEEP_WIN
    else:
        if not sheep_moves(wolves, sheep):
            return True, WOLF_WIN
    return False, None


def pos_name(p: int) -> str:
    """棋盘坐标记号: 列 A-E(左→右) + 行 1-5(下→上), 如 C3"""
    return f"{'ABCDE'[p % 5]}{5 - p // 5}"

# -*- coding: utf-8 -*-
"""胜率估计:基于"人类失误模型"的当前局面结果概率(狼胜/羊胜/和棋)。
设计(用户要求"胜率以及和棋率"):
  - AI 一方:始终走表最优(带引擎风格偏好),不失误;
  - 人类一方:85% 走最优,其余按"显眼度"加权分配(吃子/进中显眼,
    退避冷着不显眼;唯一应手局面再打 0.6 折);
  - 深度 8 回合,未分胜负处按表值折算;
  - 和棋率单列(和棋判狼胜,界面另行注明)。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, popcount,
                   wolf_moves, sheep_moves, apply_wolf_move, apply_sheep_move)
import endgame

P_BEST = 0.85
CENTER_DIST = {(r, c): max(abs(r - 2), abs(c - 2)) for r in range(5)
               for c in range(5)}

_CACHE = {}
_CACHE_LIMIT = 400000


def _clear_cache():
    if len(_CACHE) > _CACHE_LIMIT:
        _CACHE.clear()


def _salience(frm, to, cap):
    if cap:
        return 3.0
    d1 = CENTER_DIST[(frm // 5, frm % 5)]
    d2 = CENTER_DIST[(to // 5, to % 5)]
    if d2 < d1:
        return 2.0
    if d2 > d1:
        return 0.4
    return 1.0


def _human_dist(w, s, side):
    """人类走 side 一方时的走法概率分布(修剪为 最优+前3显眼,归一化)。"""
    if side == WOLF:
        moves = wolf_moves(w, s)
        def rank(mv):
            frm, to, cap = mv
            w2, s2 = apply_wolf_move(w, s, frm, to)
            if popcount(s2) <= 3:
                return 0
            v = endgame.lookup(w2, s2, SHEEP)
            return 0 if v == WOLF_WIN else (1 if v == DRAW else 2)
    else:
        moves = sheep_moves(w, s)
        def rank(mv):
            frm, to = mv
            w2, s2 = apply_sheep_move(w, s, frm, to)
            v = endgame.lookup(w2, s2, WOLF)
            return 0 if v == SHEEP_WIN else (1 if v == DRAW else 2)
    if not moves:
        return []
    rk = [rank(m) for m in moves]
    best_r = min(rk)
    # 唯一不败应手
    unique = sum(1 for r in rk if r != 2) == 1
    scored = []
    for m, r in zip(moves, rk):
        frm, to, cap = (m[0], m[1], m[2]) if side == WOLF else \
            (m[0], m[1], False)
        sal = _salience(frm, to, cap)
        if unique and r != 2:
            sal *= 0.6
        scored.append((m, r, sal))
    scored.sort(key=lambda x: (x[1], -x[2]))   # 先按档位,再按显眼度
    keep = scored[:1] + sorted(scored[1:], key=lambda x: -x[2])[:3]
    # 最优档第一招拿 P_BEST;其余按显眼度分 1-P_BEST
    dist = {keep[0][0]: P_BEST}
    for m, r, sal in keep[1:]:
        dist[m] = sal
    others = {m: p for m, p in dist.items() if p != P_BEST}
    tot = sum(others.values())
    out = []
    for m, p in dist.items():
        if p == P_BEST:
            out.append((m, P_BEST))
        elif tot > 0:
            out.append((m, p / tot * (1 - P_BEST)))
    return out


def score_position(w, s, turn, eng=None, depth=6):
    """局面评分(狼方为正,羊方为负):
      - 狼胜: +600 - d(d=精确到终局步数,越近越高,最低 +450)
      - 羊胜: -600 + d
      - 和棋: 200 * (P狼 - P羊),P 来自对称失误模型(双方都会犯错);
        始终在 ±200 内,正=狼实际占优,负=羊实际占优。
    返回 (score, p_wolf, p_sheep, p_draw)。"""
    key = (w, s, turn, depth)
    r = _CACHE.get(key)
    if r is not None:
        return r
    v = endgame.lookup(w, s, turn)
    d = endgame.lookup_dist(w, s, turn)
    if v == WOLF_WIN:
        if d is not None and d >= 0:
            r = (max(600 - d, 450), 1.0, 0.0, 0.0)
        else:
            r = (450, 1.0, 0.0, 0.0)
    elif v == SHEEP_WIN:
        if d is not None and d >= 0:
            r = (min(-600 + d, -450), 0.0, 1.0, 0.0)
        else:
            r = (-450, 0.0, 1.0, 0.0)
    else:
        pw, ps_, pd_ = estimate(w, s, turn, False, False, depth=depth,
                                eng=eng)
        r = (200.0 * (pw - ps_), pw, ps_, pd_)
    _clear_cache()
    _CACHE[key] = r
    return r


def estimate(w, s, turn, ai_wolf, ai_sheep, depth=8, eng=None, seen=None):
    """返回 (p_wolf, p_sheep, p_draw)。turn=当前走子方。
    - 已定局面(表值狼胜/羊胜)直接精确返回;
    - 同一局面在路径中再次出现(循环)=按和棋折底,终止递归;
    - depth 只是"最多算多深"的安全上限,不再是准确性硬顶
      (迭代加深:深度越深越准,直到循环折底或已定局面)。"""
    # 终局
    if popcount(s) <= 3:
        return (1.0, 0.0, 0.0)
    if turn == WOLF and not wolf_moves(w, s):
        return (0.0, 1.0, 0.0)
    if turn == SHEEP and not sheep_moves(w, s):
        return (1.0, 0.0, 0.0)
    # 已定局面:精确值(不再继续展开)
    v = endgame.lookup(w, s, turn)
    if v == WOLF_WIN:
        return (1.0, 0.0, 0.0)
    if v == SHEEP_WIN:
        return (0.0, 1.0, 0.0)
    if seen is None:
        seen = set()
    if (w, s, turn) in seen:
        return (0.0, 0.0, 1.0)   # 路径循环:按和棋折底
    if depth <= 0:
        return (0.0, 0.0, 1.0)
    seen.add((w, s, turn))
    try:
        if turn == WOLF:
            if ai_wolf and eng is not None:
                mv = eng._choose_table_move(w, s, WOLF, fast=True)
                if mv is None:
                    return (0.0, 0.0, 1.0)
                return estimate(*apply_wolf_move(w, s, mv[0], mv[1]), SHEEP,
                                ai_wolf, ai_sheep, depth - 1, eng, seen)
            dist = _human_dist(w, s, WOLF)
            pw = ps_ = pd_ = 0.0
            for m, pr in dist:
                w2, s2 = apply_wolf_move(w, s, m[0], m[1])
                if popcount(s2) <= 3:
                    pw += pr
                    continue
                sub = estimate(w2, s2, SHEEP, ai_wolf, ai_sheep,
                               depth - 1, eng, seen)
                pw += pr * sub[0]
                ps_ += pr * sub[1]
                pd_ += pr * sub[2]
            return (pw, ps_, pd_)
        else:
            if ai_sheep and eng is not None:
                mv = eng._choose_table_move(w, s, SHEEP, fast=True)
                if mv is None:
                    return (0.0, 0.0, 1.0)
                return estimate(*apply_sheep_move(w, s, mv[0], mv[1]), WOLF,
                                ai_wolf, ai_sheep, depth - 1, eng, seen)
            dist = _human_dist(w, s, SHEEP)
            pw = ps_ = pd_ = 0.0
            for m, pr in dist:
                w2, s2 = apply_sheep_move(w, s, m[0], m[1])
                sub = estimate(w2, s2, WOLF, ai_wolf, ai_sheep,
                               depth - 1, eng, seen)
                pw += pr * sub[0]
                ps_ += pr * sub[1]
                pd_ += pr * sub[2]
            return (pw, ps_, pd_)
    finally:
        seen.discard((w, s, turn))

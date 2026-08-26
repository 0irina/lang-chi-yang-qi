# -*- coding: utf-8 -*-
"""狼吃羊棋对弈引擎

- 残局表(已破解层)查询:完美胜负 + 精确到终局距离(最快取胜/最顽强抵抗)
- 未破解层(羊数 > 表上限)回退:alpha-beta 搜索 + 手写评估(临时方案)
- 和棋局面:按用户规则,优先走不重复的招法;若最优招法必然循环,
  改走次优变招让棋局继续("你不肯变招那我让你一步")
"""
import time
import random

import rules
from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, ONGOING,
                   INIT_WOLVES, INIT_SHEEP, popcount, wolf_moves, sheep_moves,
                   apply_wolf_move, apply_sheep_move, outcome, ALL_MASK, pos_name)
import endgame

try:
    from opening_book import BOOK as OPENING_BOOK
    from opening_book2 import BOOK2 as OPENING_BOOK2
except Exception:
    OPENING_BOOK = {}
    OPENING_BOOK2 = {}

try:
    import parallel_score as _pscore
except Exception:
    class _PS:
        @staticmethod
        def batch_scores(items, depth, eng=None):
            import winrate
            return [winrate.score_position(w, s, t, eng=eng, depth=depth)[0]
                    for w, s, t in items]
    _pscore = _PS()

INF = 1 << 30
WIN_SCORE = 1000000
CHAIN_W = 25       # 压力链每回合评分权重(表精确项)
CHAIN_MAX = 8      # 压力链计入上限(更长的链收益趋平)
_CHAIN_CACHE = {}  # 压力链缓存 (w,s) -> 链长


class Engine:
    def __init__(self, tt_dir=None, search_depth=6, node_budget=400_000):
        loaded = endgame.load_tables(tt_dir)
        self.table_k = max(loaded) if loaded else 0
        self.search_depth = search_depth
        self.node_budget = node_budget
        self.tt = {}      # alpha-beta 置换表 {key: (depth, score)}
        self.nodes = 0
        self.abort = False
        # 羊方开局轮换(防背谱):开局若干回合内,在和棋同档、评分接近的
        # 好棋中随机偏离主线——高手背不住所有变线,进入中盘才是羊的机会
        self.opening_variety = False
        self.score_depth = 5   # 强手模型评分深度(精准度核心参数)
        self._in_chain = False  # 压力链计算重入护栏
        self.opening_plies = 10
        self.score_margin = 12.0   # 评分相差该值以内视为同档可轮换
        self.rng = random.Random()

    # ---------- 表查询 ----------
    def value_of(self, w, s, turn):
        return endgame.lookup(w, s, turn)

    def dist_of(self, w, s, turn):
        return endgame.lookup_dist(w, s, turn)

    def _pressure_chain(self, w, s):
        """压力链(表精确):从狼走后局面 (w,s)(和棋)起,沿主变线统计
        狼连续"正招数<=2"的回合数。这是深度受限的失误模型看不到的
        长线精度压力,由全破解表精确给出(压狼=逼狼每步只能走唯一正招,
        走错即羊胜;链条越长,对手必须连续精确的时间越长)。"""
        got = _CHAIN_CACHE.get((w, s))
        if got is not None:
            return got
        if self._in_chain:
            return 0
        self._in_chain = True
        try:
            chain = 0
            cw, cs, ct = w, s, WOLF
            seen = set()
            for _ in range(CHAIN_MAX * 2):
                key = (cw, cs, ct)
                if key in seen:
                    break
                seen.add(key)
                if ct == WOLF:
                    wc = 0
                    for a, b, cap in wolf_moves(cw, cs):
                        w2, s2 = apply_wolf_move(cw, cs, a, b)
                        if popcount(s2) <= 3 or \
                                endgame.lookup(w2, s2, SHEEP) == DRAW:
                            wc += 1
                    if wc > 2:
                        break
                    chain += 1
                mv = self._choose_table_move(cw, cs, ct, fast=True,
                                             no_chain=True)
                if mv is None:
                    break
                if ct == WOLF:
                    cw, cs = apply_wolf_move(cw, cs, mv[0], mv[1])
                else:
                    cw, cs = apply_sheep_move(cw, cs, mv[0], mv[1])
                ct = 1 - ct
        finally:
            self._in_chain = False
        if len(_CHAIN_CACHE) > 2_000_000:
            _CHAIN_CACHE.clear()
        _CHAIN_CACHE[(w, s)] = chain
        return chain

    def covered(self, sheep_count):
        return sheep_count <= self.table_k

    # ---------- 结果排序(行棋方视角,0 最好) ----------
    @staticmethod
    def rank_for(v, turn):
        if turn == WOLF:
            return {WOLF_WIN: 0, DRAW: 1, SHEEP_WIN: 2}.get(v)
        return {SHEEP_WIN: 0, DRAW: 1, WOLF_WIN: 2}.get(v)

    # ---------- 最佳招法 ----------
    def best_move(self, w, s, turn, history=(), depth=None, max_len=None,
                  ply_budget=None, score_depth=None, no_chain=False):
        """history: 本局已出现的 (wolves, sheep) 列表,用于重复回避
        ply_budget: 剩余步数预算(150 步规则);必胜/必负所需步数超过预算时按和棋处理
        score_depth: 强手模型评分深度(None=引擎默认;迭代加深时逐层传入)
        no_chain: True=跳过表精确压力链(界面快路径用;不影响结果档)"""
        t0 = time.time()
        if self.covered(popcount(s)):
            move, info = self._best_from_table(w, s, turn, history, max_len,
                                               ply_budget, score_depth,
                                               no_chain)
        else:
            move, info = self._best_from_search(w, s, turn, history,
                                                depth or self.search_depth)
        info["time"] = time.time() - t0
        return move, info

    @staticmethod
    def _adj_value(v, d, ply_budget):
        """(保留但已停用)限步规则只作终局条件,不参与选招。
        选招一律按真实表值;界面按剩余步数附加"到限判狼胜"提醒。"""
        return v

    def _opp_err(self, w, s, turn):
        """对手(turn 方)在该局面下"走一步即败"的招法数,返回 (bad, total)。
        实战选招:bad/total 越大,对手越容易失误(骗招度)。"""
        bad = 0
        total = 0
        if turn == WOLF:
            for frm, to, cap in wolf_moves(w, s):
                w2, s2 = apply_wolf_move(w, s, frm, to)
                if popcount(s2) <= 3:
                    continue  # 直接吃胜(狼的胜着,不算失误;和棋后继中不存在)
                if endgame.lookup(w2, s2, SHEEP) == SHEEP_WIN:
                    bad += 1
                total += 1
        else:
            for frm, to in sheep_moves(w, s):
                w2, s2 = apply_sheep_move(w, s, frm, to)
                if endgame.lookup(w2, s2, WOLF) == WOLF_WIN:
                    bad += 1
                total += 1
        return bad, total

    def _wolf_safe_caps(self, w, s):
        """狼在该局面(狼走)下"安全吃子"的招法数:吃子且吃后不输。
        羊用它识别"会被白吃"的位置——对完美对手,这类吃子狼必走,
        羊走进去等于白送子(最后惨和)。"""
        n = 0
        for frm, to, cap in wolf_moves(w, s):
            if not cap:
                continue
            w2, s2 = apply_wolf_move(w, s, frm, to)
            if popcount(s2) <= 3:
                n += 1  # 直接吃胜(和棋后继中不会出现,防御性计数)
                continue
            if endgame.lookup(w2, s2, SHEEP) != SHEEP_WIN:
                n += 1
        return n

    def _wolf_losing_caps(self, w, s):
        """狼在该局面(狼走)下"吃子即输"的毒吃数(羊的骗招诱饵):
        狼若吃这些羊,吃后局面是羊胜。羊方偏好制造这种陷阱。"""
        n = 0
        for frm, to, cap in wolf_moves(w, s):
            if not cap:
                continue
            w2, s2 = apply_wolf_move(w, s, frm, to)
            if popcount(s2) <= 3:
                continue  # 直接吃胜,不是毒
            if endgame.lookup(w2, s2, SHEEP) == SHEEP_WIN:
                n += 1
        return n

    def _wolf_cap_threat(self, w, s):
        """狼方吃子威胁(2回合):狼走一步(非吃子)后,下一手能"安全吃子"的
        招数。羊方希望它=0:狼既吃不到羊,羊才能在保住数量的前提下慢慢围狼
        (用户思路:压缩狼空间的关键不是机动性,而是狼失去吃子能力)。"""
        n = 0
        for frm, to, cap in wolf_moves(w, s):
            if cap:
                continue  # 当前安全吃子已由 _wolf_safe_caps 计
            w2, s2 = apply_wolf_move(w, s, frm, to)
            for f2, t2, c2 in wolf_moves(w2, s2):
                if not c2:
                    continue
                w3, s3 = apply_wolf_move(w2, s2, f2, t2)
                if popcount(s3) <= 3 or \
                        endgame.lookup(w3, s3, SHEEP) != SHEEP_WIN:
                    n += 1
                    break
        return n

    def _bait_score_drop(self, w, s):
        """软诱饵的分数落差(狼走局面):狼选最安全的一手吃子后,其局面评分
        相对"不吃"下跌多少(评分体系:和棋±200,狼胜+450~600,羊胜-450~-600)。
        用户定义:软诱饵 = 让对手吃了之后分数大跌的诱饵;羊送子时优先送
        这种(送子必须换位置优势)。仅对 safe>0 的候选调用。"""
        import winrate  # 局部导入避免循环依赖
        base = winrate.score_position(w, s, WOLF, eng=self, depth=3)[0]
        worst = None  # 狼挑"吃完后分数最高"的那手吃
        for frm, to, cap in wolf_moves(w, s):
            if not cap:
                continue
            w2, s2 = apply_wolf_move(w, s, frm, to)
            if popcount(s2) <= 3:
                return -1000.0  # 狼直接吃胜:诱饵极差
            if endgame.lookup(w2, s2, SHEEP) == SHEEP_WIN:
                continue  # 毒吃,狼不会选
            sc = winrate.score_position(w2, s2, SHEEP, eng=self, depth=3)[0]
            if worst is None or sc > worst:
                worst = sc
        if worst is None:
            return 0.0
        return base - worst

    def fortress_holds(self, w, s, turn, seen, depth):
        """堡垒内层:狼(狼回合)想吃到羊(任一安全吃子=攻破),羊想维持。
        turn=当前走子方;seen={(w,s,turn)} 羊侧防重复。"""
        if popcount(s) <= 3:
            return False
        if depth <= 0:
            return True
        key = (w, s, turn)
        if key in seen:
            return True
        seen = seen | {key}
        if turn == WOLF:
            for frm, to, cap in wolf_moves(w, s):
                w2, s2 = apply_wolf_move(w, s, frm, to)
                if cap:
                    # 任一安全吃子(吃后非羊胜)= 堡垒被攻破
                    if popcount(s2) <= 3 or \
                            endgame.lookup(w2, s2, SHEEP) != SHEEP_WIN:
                        return False
                    continue
                if endgame.lookup(w2, s2, SHEEP) == SHEEP_WIN:
                    continue
                if not self.fortress_holds(w2, s2, SHEEP, seen, depth - 1):
                    return False
            return True
        for frm, to in sheep_moves(w, s):
            w2, s2 = apply_sheep_move(w, s, frm, to)
            if (w2, s2, WOLF) in seen:
                continue
            if self.fortress_holds(w2, s2, WOLF, seen, depth - 1):
                return True
        return False

    def fortress_ok(self, w, s):
        """堡垒判定(狼回合局面):狼当前无安全吃子,且8层内狼吃不到
        (羊防重复)。羊方"堡垒倾向"键:尽早进入狼永远吃不到的局面。"""
        for frm, to, cap in wolf_moves(w, s):
            if not cap:
                continue
            w2, s2 = apply_wolf_move(w, s, frm, to)
            if popcount(s2) <= 3 or \
                    endgame.lookup(w2, s2, SHEEP) != SHEEP_WIN:
                return False
        return self.fortress_holds(w, s, WOLF, frozenset(), 8)

    def _bait_danger(self, w, s):
        danger = None
        for frm, to, cap in wolf_moves(w, s):
            if not cap:
                continue
            w2, s2 = apply_wolf_move(w, s, frm, to)
            if popcount(s2) <= 3:
                return 0  # 直接吃胜,狼无危险
            if endgame.lookup(w2, s2, SHEEP) == SHEEP_WIN:
                continue  # 毒吃,狼不会选
            bad, tot = self._opp_err(w2, s2, SHEEP)
            if danger is None or bad < danger:
                danger = bad
        return danger if danger is not None else 0

    def _salient_err(self, w, s):
        """显眼败招数(狼走局面):狼的高显眼度走法(吃子3/走向中心2/一般1/
        退避0.4)中,走后直接羊胜的加权和。与强手模型 P(羊胜) 相关系数
        0.918 —— 中心阵验证:狼最自然的着法(如中狼前压)往往是败招,
        羊方应把狼的"自然着法"变成陷阱。"""
        tot = 0.0
        for frm, to, cap in wolf_moves(w, s):
            w2, s2 = apply_wolf_move(w, s, frm, to)
            if popcount(s2) <= 3:
                continue  # 直接吃胜,不是败招
            if endgame.lookup(w2, s2, SHEEP) != SHEEP_WIN:
                continue
            if cap:
                tot += 3.0
                continue
            d1 = max(abs(frm // 5 - 2), abs(frm % 5 - 2))
            d2 = max(abs(to // 5 - 2), abs(to % 5 - 2))
            if d2 < d1:
                tot += 2.0
            elif d2 > d1:
                tot += 0.4
            else:
                tot += 1.0
        return tot

    def _wolf_can_repeat(self, w, s, hist_set):
        """重复威胁检测(羊方选招用):羊的候选后继(w,s)(狼走,和棋)中,
        狼是否存在一步走回历史局面的非败应手,且羊在该历史局面 h 没有
        "仍和棋、不重复、且狼安全吃子=0(吃不到羊)"的好出路。
        有出路 = 狼重复也压不住羊(羊可换压缩狼空间的好棋);
        没出路 = 羊只能白白送子 → 该候选应降级(用户规则:送子必须换
        位置优势,不能白白送子)。"""
        if not hist_set:
            return False
        for frm, to, cap in wolf_moves(w, s):
            w3, s3 = apply_wolf_move(w, s, frm, to)
            if popcount(s3) <= 3:
                continue  # 狼直接吃胜,与重复无关
            if (w3, s3) not in hist_set:
                continue
            if endgame.lookup(w3, s3, SHEEP) == SHEEP_WIN:
                continue  # 狼不会为重复走败招
            # 羊在 h=(w3,s3) 是否有好出路:和棋 + 不重复 + 狼安全吃子=0
            good = False
            for sf, st in sheep_moves(w3, s3):
                w4, s4 = apply_sheep_move(w3, s3, sf, st)
                if (w4, s4) in hist_set or (w4, s4) == (w, s):
                    continue
                if endgame.lookup(w4, s4, WOLF) != DRAW:
                    continue
                if self._wolf_safe_caps(w4, s4) == 0:
                    good = True
                    break
            if not good:
                return True
        return False

    def _sheep_zugzwang(self, w, s, hist_set):
        """狼的重复压迫武器(用户思路):羊在该局面(羊走,和棋)没有"仍和棋、
        不重复、且狼吃不到(安全吃子=0)"的出路——羊要么重复(和棋=狼胜),
        要么变招送子。狼方应主动制造这种局面。"""
        if not hist_set:
            return False
        for sf, st in sheep_moves(w, s):
            w4, s4 = apply_sheep_move(w, s, sf, st)
            if (w4, s4) in hist_set:
                continue
            if endgame.lookup(w4, s4, WOLF) != DRAW:
                continue
            if self._wolf_safe_caps(w4, s4) == 0:
                return False   # 羊仍有"和棋+不重复+狼吃不到"的好出路
        return True

    def _wolf_eat_potential(self, w, s):
        """狼的长线吃子潜力(狼走局面):当前可安全吃子数 + 羊方最优应手后
        仍可安全吃子数。狼方和棋目标:长线吃得更多(不无脑吃,防止过早
        被围死导致后续吃不到羊 —— 用户思路)。"""
        caps = 0
        for frm, to, cap in wolf_moves(w, s):
            if not cap:
                continue
            w2, s2 = apply_wolf_move(w, s, frm, to)
            if popcount(s2) <= 3 or endgame.lookup(w2, s2, SHEEP) != SHEEP_WIN:
                caps += 1
        # 羊方最优应手之后的吃子数(内部调用,fast 模式避免递归变慢)
        smv = self._choose_table_move(w, s, SHEEP, fast=True)
        if smv is not None:
            w2, s2 = apply_sheep_move(w, s, smv[0], smv[1])
            for frm, to, cap in wolf_moves(w2, s2):
                if not cap:
                    continue
                w3, s3 = apply_wolf_move(w2, s2, frm, to)
                if popcount(s3) <= 3 or \
                        endgame.lookup(w3, s3, SHEEP) != SHEEP_WIN:
                    caps += 1
        return caps

    def _ranked_cands(self, w, s, turn, history, ply_budget, raw=False,
                      score_depth=None, no_chain=False):
        """构建并按引擎规则排序全部候选招法(供 best_move 与变招功能共用)。
        raw=True 时不做限步修正,返回真实表值(界面显示用)。
        score_depth: 强手模型评分深度(None=引擎默认)。
        【用户要求】限步规则只是终局条件,绝不参与选招:双方永远按真实
        表值走最优线(最快赢棋/最佳和棋)。羊胜限内杀不完时,羊仍走最快
        赢棋线——对方一旦失误,羊就能真的赢,不能自暴自弃改走拖延线。"""
        sd = score_depth if score_depth is not None else self.score_depth
        cands = []
        hist_set = set(history) if history else set()
        hist_cnt = {}
        if history:
            for h in history:
                hist_cnt[h] = hist_cnt.get(h, 0) + 1
        if turn == WOLF:
            wsc_items = []
            for frm, to, cap in wolf_moves(w, s):
                w2, s2 = apply_wolf_move(w, s, frm, to)
                k2 = popcount(s2)
                if k2 <= 3:
                    v, d = WOLF_WIN, 0
                else:
                    v = endgame.lookup(w2, s2, SHEEP)
                    d = endgame.lookup_dist(w2, s2, SHEEP)
                # 狼方:不应用限步修正,真实羊胜线一律避开
                if v == DRAW and hist_cnt.get((w2, s2), 0) >= 4:
                    # 重复规则:同一局面第5次出现=和棋判狼胜(狼的规则胜)
                    v, d = WOLF_WIN, 0
                if v == DRAW:
                    b, t = self._opp_err(w2, s2, SHEEP)
                    # 长线吃子潜力(用户:不无脑吃,要长线吃得更多)
                    eat = self._wolf_eat_potential(w2, s2)
                    # 走回历史局面:狼可重复不变招(和棋=狼胜),优先
                    inh = (w2, s2) in hist_set
                    # 重复压迫:走后羊只能重复或送子(用户思路)
                    zug = self._sheep_zugzwang(w2, s2, hist_set)
                    # 强手模型评分(狼方:和棋也要尽量赢;评分稍后并行批量算)
                    wsc_items.append((len(cands), w2, s2))
                    err = (b, t, eat, inh, zug, 0.0)
                else:
                    err = (0, 0, 0, False, False, 0.0)
                cands.append((frm, to, cap, v, d, err))
            if wsc_items:
                scs = _pscore.batch_scores(
                    [(w2, s2, SHEEP) for _, w2, s2 in wsc_items], sd,
                    eng=self)
                for (idx, _w2, _s2), scv in zip(wsc_items, scs):
                    frm, to, cap, v, d, err = cands[idx]
                    b, t, eat, inh, zug, _w = err
                    cands[idx] = (frm, to, cap, v, d,
                                  (b, t, eat, inh, zug, scv))
        else:
            ms = sheep_moves(w, s)
            all_c = []
            sc_items = []
            for frm, to in ms:
                w2, s2 = apply_sheep_move(w, s, frm, to)
                v = endgame.lookup(w2, s2, WOLF)
                d = endgame.lookup_dist(w2, s2, WOLF)
                # 重复规则(硬):走后狼若一步能走回"已出现4次"的局面
                # (第5次=和棋判狼胜),该候选=规则负,视为狼胜避开。
                if v == DRAW and hist_cnt:
                    for wa, wb, cap in wolf_moves(w2, s2):
                        w3, s3 = apply_wolf_move(w2, s2, wa, wb)
                        if hist_cnt.get((w3, s3), 0) >= 4:
                            v = WOLF_WIN
                            d = 0
                            break
                # 羊方:同样不应用限步修正,永远走最快赢棋线
                if v == DRAW:
                    b, t = self._opp_err(w2, s2, WOLF)
                    # 软重复键已废弃;硬规则=上方"走后狼一步走回第4次"
                    # 与"羊走后第5次出现"两处检查。
                    rep = False
                    safe = self._wolf_safe_caps(w2, s2)
                    threat = self._wolf_cap_threat(w2, s2)
                    # 软诱饵 = 狼吃后分数大跌;仅送子候选(safe>0)计算
                    drop = self._bait_score_drop(w2, s2) \
                        if safe > 0 else 0.0
                    # 注:曾加过"堡垒倾向"键(8层堡垒检查),但该检查
                    # 不可靠(16层会攻破假堡垒),已移除。
                    sc_items.append((len(all_c), w2, s2))
                    err = (b, t, safe, drop, threat,
                           self._wolf_losing_caps(w2, s2), rep,
                           self._salient_err(w2, s2), 0.0,
                           hist_cnt.get((w2, s2), 0))
                else:
                    err = (0, 0, 0, 0.0, 0, 0, False, 0.0, 0.0,
                           hist_cnt.get((w2, s2), 0))
                all_c.append((frm, to, False, v, d, err,
                              hist_cnt.get((w2, s2), 0)))
            if sc_items:
                scs = _pscore.batch_scores(
                    [(w2, s2, WOLF) for _, w2, s2 in sc_items], sd,
                    eng=self)
                for (idx, _w2, _s2), scv in zip(sc_items, scs):
                    frm, to, cap, v, d, err, _cnt = all_c[idx]
                    b, t, safe, drop, threat, poison, rep, salient, \
                        _sc, repcnt = err
                    all_c[idx] = (frm, to, cap, v, d,
                                  (b, t, safe, drop, threat, poison, rep,
                                   salient, scv, repcnt),
                                  all_c[idx][6])
            # 重复规则(用户确认):同一局面【第5次出现】才判和(羊负),
            # 第2~4次重复完全合法——唯一和棋着法即使重复也必须走,
            # 绝不能白送成真输(实战教训:game_vs_builtin_ai 第44手)。
            keep = [c for c in all_c if c[6] < 4]
            if not keep:
                keep = list(all_c)   # 全部着法都会走到第5次:挑最不亏的
            cands.extend([c[:6] for c in keep])

        # 排名:结果(越小越好) → [和棋:吃羊/骗招度] → 距离
        def key(c):
            frm, to, cap, v, d, err = c
            r = self.rank_for(v, turn)
            if r == 0:        # 我方胜:距离小好
                dk = d
            elif r == 2:      # 我方负:距离大好(顽强)
                dk = -d
            else:
                dk = 0
            if r == 1:
                if turn == WOLF:
                    bad, tot, eat, inh, zug, wsc = err
                    ratio = (bad / tot) if tot else 0.0
                    # 和棋(=到限狼胜)但也要尽量赢(用户要求):
                    # 羊正招极少(压力) → 长线吃子潜力 → 强手模型评分
                    # → 走回历史 → 重复压迫 → 先吃 → 骗招
                    scorr = tot - bad      # 走后羊的正招数(越少越好)
                    pref = (scorr, -eat, -wsc, -inh, -zug,
                            0 if cap else 1, -ratio)
                else:
                    bad, tot, safe, drop, threat, poison, rep, salient, sc, \
                        repcnt = err
                    # 羊方定稿(实战数据:人类高手=不送子+狼唯一正招
                    # 同时成立;本局引擎送子12处且压力第26手崩掉):
                    # 开局书 → 不送子 → 狼正招极少 → 狼吃不到
                    # → 模型评分 → 重复次数少 → 软诱饵 → 败招多
                    # → 显眼败招 → 毒羊
                    bm = OPENING_BOOK.get((w, s))
                    bm2 = OPENING_BOOK2.get((w, s))
                    if bm and (frm, to) in bm:
                        bk = 0      # 主选高压(狼唯一正招)
                    elif bm2 and (frm, to) in bm2:
                        bk = 1      # 次选高压(狼正招<=2)
                    else:
                        bk = 2
                    wcorr = tot - bad   # 狼走后仍和棋的正招数
                    # 模型评分 + 表精确压力链(深度受限的模型看不到的
                    # 长线精度压力,由表精确补上);no_chain=界面快路径跳过
                    sc_adj = sc
                    if not no_chain and not self._in_chain:
                        w2k, s2k = apply_sheep_move(w, s, frm, to)
                        ch = self._pressure_chain(w2k, s2k)
                        sc_adj = sc - CHAIN_W * min(ch, CHAIN_MAX)
                    pref = (bk, safe, wcorr, threat, sc_adj, repcnt, -drop,
                            -bad, -salient, -poison)
            else:
                pref = ()
            return (r,) + pref + (dk, to, frm)

        cands.sort(key=key)
        return cands

    def ranked_moves(self, w, s, turn, history=(), ply_budget=None,
                     all_ranks=False, raw=False, score_depth=None,
                     no_chain=False):
        """按引擎排序的候选招法 [(frm,to,cap), v, d]。
        all_ranks=False: 仅最优结果档(GUI"变招"用,绝不降档);
        all_ranks=True : 全部招法从优到次(GUI"候选招法"面板用);
        raw=True       : 不做限步修正,返回真实表值(界面显示用)。"""
        cands = self._ranked_cands(w, s, turn, history, ply_budget, raw=raw,
                                   score_depth=score_depth, no_chain=no_chain)
        if not cands:
            return []
        if not all_ranks:
            best_rank = self.rank_for(cands[0][3], turn)
            cands = [c for c in cands if self.rank_for(c[3], turn) == best_rank]
        return [((c[0], c[1], c[2]), c[3], c[4]) for c in cands]

    def find_trap(self, w, s, max_plies=6):
        """羊方陷阱扫描:从"羊走"的和棋局面出发,找压迫线——
        羊每步选"狼安全应手最少"的着法,狼若只剩唯一安全应手则强制沿该手续走,
        直到狼出现多条安全应手为止。返回 (首着, chain, 描述)。
        chain = [(方, frm, to, cap), ...] 双方交替;狼无需陷阱(和棋=狼胜)。"""
        chain_best = None
        for frm, to in sheep_moves(w, s):
            w2, s2 = apply_sheep_move(w, s, frm, to)
            if endgame.lookup(w2, s2, WOLF) != DRAW:
                continue  # 只狩猎和棋压迫线(直接羊胜无需陷阱)
            chain = [("羊", frm, to, False)]
            cw, cs, ct = w2, s2, WOLF
            for _ in range(max_plies - 1):
                if ct == WOLF:
                    safe = []
                    for wf, wt_, wc in wolf_moves(cw, cs):
                        ww, ss = apply_wolf_move(cw, cs, wf, wt_)
                        if popcount(ss) <= 3 or \
                                endgame.lookup(ww, ss, SHEEP) != SHEEP_WIN:
                            safe.append((wf, wt_, wc))
                    if len(safe) == 1:
                        wf, wt_, wc = safe[0]
                        ww, ss = apply_wolf_move(cw, cs, wf, wt_)
                        chain.append(("狼", wf, wt_, wc))
                        cw, cs, ct = ww, ss, SHEEP
                    else:
                        break
                else:
                    best_n = None
                    for sf, st_ in sheep_moves(cw, cs):
                        ww, ss = apply_sheep_move(cw, cs, sf, st_)
                        if endgame.lookup(ww, ss, WOLF) != DRAW:
                            continue
                        n = 0
                        for wf, wt_, wc in wolf_moves(ww, ss):
                            w3, s3 = apply_wolf_move(ww, ss, wf, wt_)
                            if popcount(s3) <= 3 or \
                                    endgame.lookup(w3, s3, SHEEP) != SHEEP_WIN:
                                n += 1
                        if n == 0:
                            continue
                        if best_n is None or n < best_n[0]:
                            best_n = (n, (sf, st_))
                    if best_n is None:
                        break
                    sf, st_ = best_n[1]
                    ww, ss = apply_sheep_move(cw, cs, sf, st_)
                    chain.append(("羊", sf, st_, False))
                    cw, cs, ct = ww, ss, WOLF
            if chain_best is None or len(chain) > len(chain_best):
                chain_best = chain
        if not chain_best:
            return None, [], "当前局面无法形成唯一应手陷阱"
        first = chain_best[0]
        desc = ("陷阱线(" + str(len(chain_best) // 2) + "回合压迫): " +
                " / ".join(f"{nm} {pos_name(a)}→{pos_name(b)}"
                           f"{'吃' if cp else ''}"
                           for nm, a, b, cp in chain_best))
        return (first[1], first[2], first[3]), chain_best, desc

    def _best_from_table(self, w, s, turn, history, max_len=None,
                         ply_budget=None, score_depth=None, no_chain=False):
        cands = self._ranked_cands(w, s, turn, history, ply_budget,
                                   score_depth=score_depth,
                                   no_chain=no_chain)
        if not cands:
            return None, dict(value=ONGOING, dist=-1, n=0, table=True)
        # 高压走廊开局书:羊方在书内局面时,只在书内走法间轮换(防背谱);
        # 主选书(狼唯一正招)优先,无主选时用次选书(狼正招<=2)。
        book_used = False
        if turn == SHEEP:
            hits = []
            if (w, s) in OPENING_BOOK:
                hits = [c for c in cands
                        if (c[0], c[1]) in OPENING_BOOK[(w, s)]]
            if not hits and (w, s) in OPENING_BOOK2:
                hits = [c for c in cands
                        if (c[0], c[1]) in OPENING_BOOK2[(w, s)]]
            if hits:
                cand = (self.rng.choice(hits) if self.opening_variety
                        else hits[0])
                cands = [cand] + [c for c in cands if c is not cand]
                book_used = True
        # 羊方开局轮换(防背谱):开局若干回合内,在与最优同档(同结果、
        # 同防御前缀)且评分接近的好棋中随机偏离主线。狼方不轮换
        # (狼巴不得走熟的和棋主线,和棋=狼胜)。
        if (not book_used and self.opening_variety and turn == SHEEP
                and len(history) <= self.opening_plies
                and len(cands) > 1):
            top = cands[0]
            t_rep = top[5][6]
            t_safe = top[5][2]
            t_thr = top[5][4]
            t_sc = top[5][8]
            pool = [c for c in cands
                    if c[3] == top[3] and c[5][6] == t_rep
                    and c[5][2] == t_safe and c[5][4] == t_thr
                    and c[5][8] <= t_sc + self.score_margin]
            # 硬门槛:轮换候选不得让狼下一步有安全吃子(避免偏离直接送羊)
            pool_safe = [c for c in pool if c[5][2] == 0]
            if pool_safe:
                pool = pool_safe
            if len(pool) > 1:
                cand = self.rng.choice(pool)
                cands = [cand] + [c for c in cands if c != cand]
        frm, to, cap, v, d, err = cands[0]
        # 原始表值(限步降级只作用于选招,界面仍以真实表值为准)
        if turn == WOLF:
            w2, s2 = apply_wolf_move(w, s, frm, to)
            nxt = SHEEP
        else:
            w2, s2 = apply_sheep_move(w, s, frm, to)
            nxt = WOLF
        if popcount(s2) <= 3:
            rv, rd = WOLF_WIN, 0
        else:
            rv = endgame.lookup(w2, s2, nxt)
            rd = endgame.lookup_dist(w2, s2, nxt)
        info = dict(value=v, dist=d, raw_value=rv, raw_dist=rd,
                    n=len(cands), table=True,
                    pv=self.pv(w, s, turn, max_len))
        return (frm, to, cap), info

    def _choose_table_move(self, w, s, turn, fast=False, no_chain=False,
                           score_depth=None):
        """仅选出表最优招法(不含 PV),供 pv() 使用,避免递归。
        fast=True 时跳过模型评分/软诱饵计算(内部调用与胜率估计用,
        避免递归变慢;真实选招走 _ranked_cands 全量评分)。"""
        sd = score_depth if score_depth is not None else self.score_depth
        hist = set()
        if turn == WOLF:
            cands = []
            for frm, to, cap in wolf_moves(w, s):
                w2, s2 = apply_wolf_move(w, s, frm, to)
                if popcount(s2) <= 3:
                    v, d = WOLF_WIN, 0
                    err = (0, 0, 0, False, False, 0.0)
                else:
                    v = endgame.lookup(w2, s2, SHEEP)
                    d = endgame.lookup_dist(w2, s2, SHEEP)
                    if v == DRAW:
                        b, t = self._opp_err(w2, s2, SHEEP)
                        eat = self._wolf_eat_potential(w2, s2)
                        wsc = 0.0
                        if not fast:
                            import winrate as _wr
                            wsc = _wr.score_position(w2, s2, SHEEP,
                                                     eng=self, depth=sd)[0]
                        err = (b, t, eat, False, False, wsc)
                    else:
                        err = (0, 0, 0, False, False, 0.0)
                cands.append((frm, to, cap, v, d, err))
        else:
            cands = []
            for frm, to in sheep_moves(w, s):
                w2, s2 = apply_sheep_move(w, s, frm, to)
                v = endgame.lookup(w2, s2, WOLF)
                d = endgame.lookup_dist(w2, s2, WOLF)
                if v == DRAW:
                    b, t = self._opp_err(w2, s2, WOLF)
                    safe = self._wolf_safe_caps(w2, s2)
                    threat = self._wolf_cap_threat(w2, s2)
                    drop = (self._bait_score_drop(w2, s2)
                            if safe > 0 and not fast else 0.0)
                    sc = 0.0
                    if not fast:
                        import winrate as _wr
                        sc = _wr.score_position(w2, s2, WOLF, eng=self,
                                                depth=sd)[0]
                    err = (b, t, safe, drop, threat,
                           self._wolf_losing_caps(w2, s2), False,
                           self._salient_err(w2, s2), sc, 0)
                else:
                    err = (0, 0, 0, 0.0, 0, 0, False, 0.0, 0.0, 0)
                cands.append((frm, to, False, v, d, err))
        def key(c):
            frm, to, cap, v, d, err = c
            r = self.rank_for(v, turn)
            if r == 0:
                dk = d
            elif r == 2:
                dk = -d
            else:
                dk = 0
            if r == 1:
                if turn == WOLF:
                    bad, tot, eat, inh, zug, wsc = err
                    ratio = (bad / tot) if tot else 0.0
                    # 与 _ranked_cands 同键(hist 恒为空,inh/zug 恒 False)
                    scorr = tot - bad
                    pref = (scorr, -eat, -wsc, -inh, -zug,
                            0 if cap else 1, -ratio)
                else:
                    bad, tot, safe, drop, threat, poison, rep, salient, sc, \
                        repcnt = err
                    # 和棋且羊走:与 _ranked_cands 同键(定稿)
                    # (hist 恒为空,rep/repcnt 恒 0/False)
                    bm = OPENING_BOOK.get((w, s))
                    bm2 = OPENING_BOOK2.get((w, s))
                    if bm and (frm, to) in bm:
                        bk = 0
                    elif bm2 and (frm, to) in bm2:
                        bk = 1
                    else:
                        bk = 2
                    wcorr = tot - bad
                    sc_adj = sc
                    if not no_chain and not fast:
                        w2k, s2k = apply_sheep_move(w, s, frm, to)
                        ch = self._pressure_chain(w2k, s2k)
                        sc_adj = sc - CHAIN_W * min(ch, CHAIN_MAX)
                    pref = (bk, safe, wcorr, threat, sc_adj, repcnt, -drop,
                            -bad, -salient, -poison)
            else:
                pref = ()
            return (r,) + pref + (dk, to, frm)
        cands.sort(key=key)
        return cands[0]

    def pv(self, w, s, turn, max_len=None):
        """破解线:从当前局面沿最优招法走(表覆盖范围内),返回描述列表"""
        if max_len is None:
            max_len = 12
        line = []
        seen = set()
        w, s, t = w, s, turn
        for _ in range(max_len):
            key = (w, s, t)
            if key in seen:
                line.append("(循环)")
                break
            seen.add(key)
            k = popcount(s)
            if k <= 3:
                line.append("狼胜(羊剩3只)")
                break
            if k > self.table_k:
                line.append("…(超出破解层)")
                break
            v = endgame.lookup(w, s, t)
            if v == DRAW:
                line.append("和棋")
                break
            mv = self._choose_table_move(w, s, t, fast=True)
            if mv is None:
                break
            frm, to, cap, vv, dd = mv[:5]
            if t == WOLF:
                w, s = apply_wolf_move(w, s, frm, to)
            else:
                w, s = apply_sheep_move(w, s, frm, to)
            who = "狼" if t == WOLF else "羊"
            tag = "吃!" if cap else ""
            line.append(f"{who} {pos_name(frm)}→{pos_name(to)}{tag}")
            if popcount(s) <= 3:
                line.append("狼胜")
                break
            if not wolf_moves(w, s):
                line.append("羊胜")
                break
            t = 1 - t
        return line

    # ---------- 未破解层:限时迭代加深 alpha-beta 回退 ----------
    def _best_from_search(self, w, s, turn, history, depth):
        best = None
        best_score = None
        self.tt = {}
        self.nodes = 0
        self.abort = False
        for d in range(2, depth + 1):
            score, mv = self._root_search(w, s, turn, d)
            if self.abort:
                break
            best_score, best = score, mv
        info = dict(value=None, dist=None, repeat=False, table=False,
                    score=best_score, nodes=self.nodes, pv=[])
        return best, info

    def _root_search(self, w, s, turn, depth):
        best = None
        if turn == WOLF:
            best_score = -INF
            moves = wolf_moves(w, s)
            moves.sort(key=lambda m: not m[2])
            for frm, to, cap in moves:
                w2, s2 = apply_wolf_move(w, s, frm, to)
                sc = self._search(w2, s2, SHEEP, depth - 1, -INF, INF)
                if sc > best_score:
                    best_score, best = sc, (frm, to, cap)
                if self.abort:
                    break
        else:
            best_score = INF
            for frm, to in sheep_moves(w, s):
                w2, s2 = apply_sheep_move(w, s, frm, to)
                sc = self._search(w2, s2, WOLF, depth - 1, -INF, INF)
                if sc < best_score:
                    best_score, best = sc, (frm, to, False)
                if self.abort:
                    break
        return best_score, best

    def _search(self, w, s, turn, depth, alpha, beta):
        """狼方视角分数:胜 +WIN_SCORE,负 -WIN_SCORE,和 0,其余评估分"""
        self.nodes += 1
        if self.nodes > self.node_budget:
            self.abort = True
            return 0
        term, winner = outcome(w, s, turn)
        if term:
            return WIN_SCORE if winner == WOLF_WIN else -WIN_SCORE
        k = popcount(s)
        if k <= self.table_k:
            v = endgame.lookup(w, s, turn)
            return {WOLF_WIN: WIN_SCORE, SHEEP_WIN: -WIN_SCORE, DRAW: 0}[v]
        if depth <= 0:
            return self._eval(w, s)
        key = (w, s, turn, depth)
        if key in self.tt:
            return self.tt[key]
        if turn == WOLF:
            best = -INF
            moves = wolf_moves(w, s)
            moves.sort(key=lambda m: not m[2])  # 吃子优先
            for frm, to, cap in moves:
                w2, s2 = apply_wolf_move(w, s, frm, to)
                sc = self._search(w2, s2, SHEEP, depth - 1, alpha, beta)
                if sc > best:
                    best = sc
                if best > alpha:
                    alpha = best
                if alpha >= beta:
                    break
        else:
            best = INF
            for frm, to in sheep_moves(w, s):
                w2, s2 = apply_sheep_move(w, s, frm, to)
                sc = self._search(w2, s2, WOLF, depth - 1, alpha, beta)
                if sc < best:
                    best = sc
                if best < beta:
                    beta = best
                if alpha >= beta:
                    break
        self.tt[key] = best
        if len(self.tt) > 2_000_000:
            self.tt.clear()
        return best

    @staticmethod
    def _eval(w, s):
        """临时评估(狼方视角)。终局优先于评估调用。"""
        k = popcount(s)
        wm = wolf_moves(w, s)
        if not wm:
            return -WIN_SCORE
        sm = sheep_moves(w, s)
        score = 0.0
        score -= 250 * k
        score += 25 * len(wm)
        score -= len(sm)
        x = w
        while x:
            lsb = x & -x
            p = lsb.bit_length() - 1
            x ^= lsb
            score += 3 * (p // 5)
        score += 40 * sum(1 for m in wm if m[2])
        return int(score)

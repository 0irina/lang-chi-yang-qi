# -*- coding: utf-8 -*-
"""无头测试:和棋局面的"实战偏好"行为。
断言:
  1) 随机和棋局面(狼走),最佳招法的结果仍是和棋(绝不牺牲结果去吃羊);
  2) 狼方和棋偏好:长线吃子潜力最大优先(不无脑吃),同潜力时先吃,
     再选骗招度最高;
  3) 分析箭头用的 _choose_table_move 与 best_move 选择一致(箭头=AI实际走法);
  4) 羊方和棋偏好:避重复陷阱 → 开局书 → 不送子 → 狼正招极少 → 软诱饵
     → 狼吃子威胁小 → 模型评分 → 败招多 → 显眼败招 → 毒羊诱饵;
  5) 重复回避:和棋=羊负,该变招的是羊;狼可重复不变招。
"""
import random
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules import WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, wolf_moves, \
    sheep_moves, apply_wolf_move, apply_sheep_move, popcount, pos_name
import endgame
import winrate
import opening_book
import opening_book2
from engine import Engine

eng = Engine()
rng = random.Random(99)


def wolf_key(w, s, m, hist_set=None):
    """狼方和棋候选的排序键(与引擎一致):
    (羊正招极少, -长线吃子, -强手模型评分, -走回历史, -重复压迫, 先吃, -骗招度)"""
    ww, ss = apply_wolf_move(w, s, m[0], m[1])
    b, t = eng._opp_err(ww, ss, SHEEP)
    ratio = b / t if t else 0.0
    scorr = t - b
    eat = eng._wolf_eat_potential(ww, ss)
    wsc = winrate.score_position(ww, ss, SHEEP, eng=eng,
                                 depth=eng.score_depth)[0]
    if hist_set:
        inh = (ww, ss) in hist_set
        zug = eng._sheep_zugzwang(ww, ss, hist_set)
        return (scorr, -eat, -wsc, -inh, -zug, 0 if m[2] else 1, -ratio)
    return (scorr, -eat, -wsc, 0, 0, 0 if m[2] else 1, -ratio)


n = 0
n_cap_avail = 0
bad = 0
mism_arrow = 0
trials = 0
while n < 200 and trials < 150000:
    trials += 1
    k = rng.choice([4, 5, 6, 7, 8])
    cells = rng.sample(range(25), 3 + k)
    w = sum(1 << c for c in cells[:3])
    s = sum(1 << c for c in cells[3:])
    if endgame.lookup(w, s, WOLF) != DRAW:
        continue
    n += 1
    mv, info = eng.best_move(w, s, WOLF, history=())
    if info["value"] != DRAW:
        bad += 1
        print(f"  [失败] 和棋局面选了非和棋: value={info['value']} mv={mv}")
        continue
    # 是否存在"吃子且吃后仍和棋"的招法(统计用)
    cap_draw = [m for m in wolf_moves(w, s)
                if m[2] and endgame.lookup(*apply_wolf_move(w, s, m[0], m[1]),
                                           SHEEP) == DRAW]
    if cap_draw:
        n_cap_avail += 1
    # 引擎选招必须 = 全候选按 wolf_key 最小
    best_key = None
    for m in wolf_moves(w, s):
        ww, ss = apply_wolf_move(w, s, m[0], m[1])
        if endgame.lookup(ww, ss, SHEEP) != DRAW:
            continue
        kk = wolf_key(w, s, m)
        if best_key is None or kk < best_key:
            best_key = kk
    got_key = wolf_key(w, s, mv)
    if best_key is not None and got_key != best_key:
        bad += 1
        if bad <= 5:
            print(f"  [失败] 狼选招非最优键: got={got_key} best={best_key}")
    # 箭头一致性
    tmv = eng._choose_table_move(w, s, WOLF)
    if (tmv[0], tmv[1], tmv[2]) != mv:
        mism_arrow += 1
        if mism_arrow <= 3:
            print(f"  [箭头不一致] best={mv} table={tmv[:3]}")

print(f"抽样 {n} 个和棋局面(狼走), 其中存在安全吃子的 {n_cap_avail} 个")
print(f"失败数: 结果牺牲={bad} 箭头不一致={mism_arrow}")

# ---- 狼/羊偏好键逐例核对 ----
n_w = n_s = 0
bad_w = bad_s = 0
trials = 0
while trials < 300000:
    trials += 1
    k = rng.choice([4, 5, 6, 7, 8])
    cells = rng.sample(range(25), 3 + k)
    w = sum(1 << c for c in cells[:3])
    s = sum(1 << c for c in cells[3:])
    if endgame.lookup(w, s, WOLF) == DRAW:
        if n_w < 80:
            n_w += 1
            mv, info = eng.best_move(w, s, WOLF, history=())
            if info["value"] == DRAW:
                best_key = None
                for m in wolf_moves(w, s):
                    ww, ss = apply_wolf_move(w, s, m[0], m[1])
                    if endgame.lookup(ww, ss, SHEEP) != DRAW:
                        continue
                    kk = wolf_key(w, s, m)
                    if best_key is None or kk < best_key:
                        best_key = kk
                if wolf_key(w, s, mv) != best_key:
                    bad_w += 1
                    if bad_w <= 3:
                        print(f"  [狼·长线吃子键] got={wolf_key(w, s, mv)} "
                              f"best={best_key}")
    if endgame.lookup(w, s, SHEEP) == DRAW:
        if n_s < 80:
            n_s += 1
            mv, info = eng.best_move(w, s, SHEEP, history=())
            if info["value"] != DRAW:
                bad_s += 1
                continue
            w2, s2 = apply_sheep_move(w, s, mv[0], mv[1])
            got_safe = eng._wolf_safe_caps(w2, s2)
            got_poison = eng._wolf_losing_caps(w2, s2)
            got_thr = eng._wolf_cap_threat(w2, s2)
            got_sal = eng._salient_err(w2, s2)
            got_bad, got_tot = eng._opp_err(w2, s2, WOLF)
            got_wcorr = got_tot - got_bad
            got_rep = eng._wolf_can_repeat(w2, s2, set())
            gbm = opening_book.BOOK.get((w, s))
            gbm2 = opening_book2.BOOK2.get((w, s))
            if gbm and (mv[0], mv[1]) in gbm:
                got_bk = 0
            elif gbm2 and (mv[0], mv[1]) in gbm2:
                got_bk = 1
            else:
                got_bk = 2
            got_drop = eng._bait_score_drop(w2, s2) if got_safe > 0 else 0.0
            got_score = winrate.score_position(w2, s2, WOLF, eng=eng,
                                               depth=eng.score_depth)[0]
            # 引擎羊方和棋偏好(定稿):(开局书) → (安全吃子少) →
            # (狼正招极少) → (狼吃子威胁小) → (模型评分低) →
            # (重复次数少) → (软诱饵落差大) → (败招多) → (显眼败招多)
            # → (毒羊)
            best = None
            for frm, to in sheep_moves(w, s):
                ww, ss = apply_sheep_move(w, s, frm, to)
                if endgame.lookup(ww, ss, WOLF) != DRAW:
                    continue
                bmn = opening_book.BOOK.get((w, s))
                bmn2 = opening_book2.BOOK2.get((w, s))
                if bmn and (frm, to) in bmn:
                    bkn = 0
                elif bmn2 and (frm, to) in bmn2:
                    bkn = 1
                else:
                    bkn = 2
                sc = eng._wolf_safe_caps(ww, ss)
                ps = eng._wolf_losing_caps(ww, ss)
                dp = eng._bait_score_drop(ww, ss) if sc > 0 else 0.0
                thr = eng._wolf_cap_threat(ww, ss)
                sal = eng._salient_err(ww, ss)
                badn, totn = eng._opp_err(ww, ss, WOLF)
                wc = totn - badn          # 狼正招数
                scm = winrate.score_position(ww, ss, WOLF, eng=eng,
                                             depth=eng.score_depth)[0]
                chn = eng._pressure_chain(ww, ss)
                sca = scm - 25 * min(chn, 8)   # 模型评分+表精确压力链
                key = (bkn, sc, wc, thr, sca, 0, -dp, -badn, -sal, -ps)
                if best is None or key < best:
                    best = key
            best_bk, best_sc, best_wc, best_thr, best_scm, best_rc, \
                neg_dp, neg_bad, neg_sal, neg_ps = best
            got_chn = eng._pressure_chain(w2, s2)
            got_sca = got_score - 25 * min(got_chn, 8)
            if (got_bk != best_bk
                    or got_safe != best_sc or got_wcorr != best_wc
                    or got_thr != best_thr
                    or got_sca > best_scm + 1e-6
                    or got_drop + 1e-9 < -neg_dp
                    or got_bad != -neg_bad
                    or got_sal + 1e-9 < -neg_sal
                    or -got_poison != neg_ps):
                bad_s += 1
                print(f"  [羊·键核对] bk={got_bk}(min={best_bk}) "
                      f"safe={got_safe}(min={best_sc}) "
                      f"wcorr={got_wcorr}(min={best_wc}) "
                      f"threat={got_thr}(min={best_thr}) "
                      f"score_adj={got_sca:.0f}(min={best_scm:.0f}) "
                      f"drop={got_drop:.0f}(max={-neg_dp:.0f}) "
                      f"bad={got_bad}(max={-neg_bad}) "
                      f"salient={got_sal:.2f}(max={-neg_sal:.2f}) "
                      f"poison={got_poison}")
    if n_w >= 80 and n_s >= 80:
        break

print(f"狼侧无吃子骗招度检查 {n_w} 个, 失败 {bad_w}; 羊侧骗招度检查 {n_s} 个, 失败 {bad_s}")

# ---- 重复规则(用户确认):同一局面第5次出现判和(羊负) ----
# 羊:第2~4次重复合法;走到第5次=羊负,有其他出路时必须回避。
# 狼:能走到第5次=规则胜(和棋判狼胜),应主动识别并选择。
n_rep = 0
bad_rep5 = 0
bad_wolf5 = 0
trials = 0
while n_rep < 60 and trials < 200000:
    trials += 1
    k = rng.choice([5, 6, 7, 8])
    cells = rng.sample(range(25), 3 + k)
    w = sum(1 << c for c in cells[:3])
    s = sum(1 << c for c in cells[3:])
    if endgame.lookup(w, s, SHEEP) != DRAW:
        continue
    mv, info = eng.best_move(w, s, SHEEP, history=())
    if mv is None or info["value"] != DRAW:
        continue
    w2, s2 = apply_sheep_move(w, s, mv[0], mv[1])
    if len(sheep_moves(w, s)) < 2:
        continue
    # 羊:后继已出现4次 → 再走=第5次=羊负,有其他和棋出路时必须回避
    dm = [(a, b) for a, b in sheep_moves(w, s)
          if endgame.lookup(*apply_sheep_move(w, s, a, b), WOLF) == DRAW]
    if any(apply_sheep_move(w, s, a, b) == (w2, s2) for a, b in dm):
        alt = [(a, b) for a, b in dm
               if apply_sheep_move(w, s, a, b) != (w2, s2)]
        if alt:
            mv2, _ = eng.best_move(w, s, SHEEP, history=((w2, s2),) * 4)
            w3, s3 = apply_sheep_move(w, s, mv2[0], mv2[1])
            if (w3, s3) == (w2, s2):
                bad_rep5 += 1
                if bad_rep5 <= 3:
                    print(f"  [羊·第5次重复未回避] "
                          f"{pos_name(mv[0])}→{pos_name(mv[1])}")
    n_rep += 1
    # 狼:存在一步走回"已出现4次"的局面 → 规则胜(第5次=和棋判狼胜)
    if endgame.lookup(w, s, WOLF) == DRAW:
        can5 = [(a, b, cap) for a, b, cap in wolf_moves(w, s)
                if apply_wolf_move(w, s, a, b) == (w2, s2)]
        if can5:
            wmv, winfo = eng.best_move(w, s, WOLF, history=((w2, s2),) * 4)
            if wmv is None or (wmv[0], wmv[1]) not in \
                    {(a, b) for a, b, c in can5} or \
                    winfo["value"] != WOLF_WIN:
                bad_wolf5 += 1
                if bad_wolf5 <= 3:
                    print(f"  [狼·规则胜未识别] 候选={can5} got={wmv}")
print(f"重复规则(5次判和): 羊侧 {n_rep} 例(第5次未回避 {bad_rep5}), "
      f"狼侧规则胜识别失败 {bad_wolf5}")

# ---- 重复规则硬检查(5次判和):羊走后不能让狼一步走回"第4次出现"局面 ----
n_z = 0
bad_z = 0
trials = 0
while n_z < 25 and trials < 400000:
    trials += 1
    k = rng.choice([5, 6, 7, 8])
    cells = rng.sample(range(25), 3 + k)
    w = sum(1 << c for c in cells[:3])
    s = sum(1 << c for c in cells[3:])
    if endgame.lookup(w, s, SHEEP) != DRAW:
        continue
    # 朴素主线自对弈8回合构成历史
    hist = [(w, s)]
    cw, cs, ct = w, s, SHEEP
    for _ in range(8):
        mvc = eng._choose_table_move(cw, cs, ct, fast=True)
        if mvc is None:
            break
        if ct == SHEEP:
            cw, cs = apply_sheep_move(cw, cs, mvc[0], mvc[1])
        else:
            cw, cs = apply_wolf_move(cw, cs, mvc[0], mvc[1])
        hist.append((cw, cs))
        ct = 1 - ct
    if len(hist) < 5:
        continue
    # 是否存在"羊走后狼一步走回4次出现局面"的危险候选
    danger = False
    for m in sheep_moves(w, s):
        aw, as_ = apply_sheep_move(w, s, m[0], m[1])
        if endgame.lookup(aw, as_, WOLF) != DRAW:
            continue
        for wm in wolf_moves(aw, as_):
            ww, ss = apply_wolf_move(aw, as_, wm[0], wm[1])
            if hist.count((ww, ss)) >= 4:
                danger = True
                break
        if danger:
            break
    if not danger:
        continue
    n_z += 1
    mv, _ = eng.best_move(w, s, SHEEP, history=tuple(hist))
    w2, s2 = apply_sheep_move(w, s, mv[0], mv[1])
    for wm in wolf_moves(w2, s2):
        ww, ss = apply_wolf_move(w2, s2, wm[0], wm[1])
        if hist.count((ww, ss)) >= 4:
            bad_z += 1
            if bad_z <= 3:
                print(f"  [羊·走后狼规则胜] {pos_name(mv[0])}→{pos_name(mv[1])}")
            break
print(f"重复规则硬检查: 危险局面 {n_z} 例, 未回避 {bad_z}")

# ---- 狼的重复压迫(用户思路):狼主动制造"羊只能重复或送子"的局面 ----
n_wz = 0
bad_wz = 0
trials = 0
while n_wz < 25 and trials < 400000:
    trials += 1
    k = rng.choice([5, 6, 7, 8])
    cells = rng.sample(range(25), 3 + k)
    w = sum(1 << c for c in cells[:3])
    s = sum(1 << c for c in cells[3:])
    if endgame.lookup(w, s, WOLF) != DRAW:
        continue
    # 朴素主线自对弈8回合,构成历史
    hist = [(w, s)]
    cw, cs, ct = w, s, WOLF
    for _ in range(8):
        mvc = eng._choose_table_move(cw, cs, ct, fast=True)
        if mvc is None:
            break
        if ct == SHEEP:
            cw, cs = apply_sheep_move(cw, cs, mvc[0], mvc[1])
        else:
            cw, cs = apply_wolf_move(cw, cs, mvc[0], mvc[1])
        hist.append((cw, cs))
        ct = 1 - ct
    if len(hist) < 5:
        continue
    hist_set = set(hist)
    # 是否存在"走后羊陷入重复压迫"的候选
    has_zug = False
    for m in wolf_moves(w, s):
        ww, ss = apply_wolf_move(w, s, m[0], m[1])
        if endgame.lookup(ww, ss, SHEEP) != DRAW:
            continue
        if eng._sheep_zugzwang(ww, ss, hist_set):
            has_zug = True
            break
    if not has_zug:
        continue
    n_wz += 1
    mv, _ = eng.best_move(w, s, WOLF, history=tuple(hist_set))
    best_key = None
    for m in wolf_moves(w, s):
        ww, ss = apply_wolf_move(w, s, m[0], m[1])
        if endgame.lookup(ww, ss, SHEEP) != DRAW:
            continue
        kk = wolf_key(w, s, m, hist_set)
        if best_key is None or kk < best_key:
            best_key = kk
    if wolf_key(w, s, mv, hist_set) != best_key:
        bad_wz += 1
        if bad_wz <= 3:
            print(f"  [狼·重复压迫键] got={wolf_key(w, s, mv, hist_set)} "
                  f"best={best_key}")
print(f"狼重复压迫: 触发 {n_wz} 例, 键不符 {bad_wz}")
print("RESULT:", "ALL OK" if (bad == 0 and mism_arrow == 0 and n_cap_avail > 20
                              and bad_w == 0 and bad_s == 0
                              and bad_rep5 == 0 and bad_wolf5 == 0
                              and bad_z == 0 and n_z >= 4
                              and bad_wz == 0 and n_wz >= 10)
      else "FAIL")

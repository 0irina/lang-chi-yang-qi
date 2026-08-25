# -*- coding: utf-8 -*-
"""策略数据研究(新表):统计和棋局面下,后继局面的特征与"对手一步失误率"的关系,
为羊方/狼方的和棋选招偏好定权重。特征:
  羊方视角(羊走完后的局面,轮到狼):
    safe    = 狼可安全白吃的招数(不送子)
    mob     = 狼机动性(可走步数,压缩狼空间思路)
    cent    = 羊占中四角数(B2,B4,D2,D4 = 格子 6,8,16,18)
    poison  = 狼"吃子即输"的毒吃数
    err1r   = 狼一步失误率(狼走一步直接变羊胜的比例)
    uniq    = 狼只剩唯一和棋应手(精度要求)
  狼方视角(狼走完后的局面,轮到羊):
    cap     = 这步是否吃子
    fcaps   = 后继局面狼仍可吃子的招数(长线吃子潜力)
    mob     = 狼机动性
    err1r   = 羊一步失误率(羊走一步直接变狼胜的比例)
"""
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, popcount,
                   wolf_moves, sheep_moves, apply_wolf_move, apply_sheep_move)
import endgame

rng = random.Random(20260824)
CENTER = {6, 8, 16, 18}
endgame.load_tables()  # 加载新规则全破解表
print("tables loaded:", endgame._FULL is not None)


def sheep_side_sample(n_target=1500):
    rows = []
    trials = 0
    while len(rows) < n_target and trials < 400000:
        trials += 1
        k = rng.choice([5, 6, 7, 8, 9, 10])
        cells = rng.sample(range(25), 3 + k)
        w = sum(1 << c for c in cells[:3])
        s = sum(1 << c for c in cells[3:])
        if endgame.lookup(w, s, SHEEP) != DRAW:
            continue
        for frm, to in sheep_moves(w, s):
            w2, s2 = apply_sheep_move(w, s, frm, to)
            if endgame.lookup(w2, s2, WOLF) != DRAW:
                continue
            safe = 0
            for wf, wt, cap in wolf_moves(w2, s2):
                w3, s3 = apply_wolf_move(w2, s2, wf, wt)
                if popcount(s3) <= 3 or endgame.lookup(w3, s3, SHEEP) != SHEEP_WIN:
                    safe += 1
            mob = len(wolf_moves(w2, s2))
            cent = popcount(s2 & sum(1 << c for c in CENTER))
            poison = 0
            err1 = 0
            tot = 0
            draws = 0
            for wf, wt, cap in wolf_moves(w2, s2):
                w3, s3 = apply_wolf_move(w2, s2, wf, wt)
                if popcount(s3) <= 3:
                    continue  # 直接吃胜不算失误
                v = endgame.lookup(w3, s3, SHEEP)
                tot += 1
                if v == SHEEP_WIN:
                    err1 += 1
                elif v == DRAW:
                    draws += 1
                if cap:
                    w4, s4 = apply_wolf_move(w2, s2, wf, wt)
                    if popcount(s4) <= 3 or \
                            endgame.lookup(w4, s4, SHEEP) != SHEEP_WIN:
                        pass
            rows.append(dict(safe=safe, mob=mob, cent=cent, poison=poison,
                             err1r=(err1 / tot if tot else 0.0),
                             uniq=(draws == 1 and err1 == 0)))
    return rows


def wolf_side_sample(n_target=1500):
    rows = []
    trials = 0
    while len(rows) < n_target and trials < 400000:
        trials += 1
        k = rng.choice([5, 6, 7, 8, 9, 10])
        cells = rng.sample(range(25), 3 + k)
        w = sum(1 << c for c in cells[:3])
        s = sum(1 << c for c in cells[3:])
        if endgame.lookup(w, s, WOLF) != DRAW:
            continue
        for frm, to, cap in wolf_moves(w, s):
            w2, s2 = apply_wolf_move(w, s, frm, to)
            if popcount(s2) <= 3 or endgame.lookup(w2, s2, SHEEP) != DRAW:
                continue
            fcaps = 0
            for wf, wt, c2 in wolf_moves(w2, s2):
                if c2:
                    w3, s3 = apply_wolf_move(w2, s2, wf, wt)
                    if popcount(s3) <= 3 or \
                            endgame.lookup(w3, s3, SHEEP) != SHEEP_WIN:
                        fcaps += 1
            mob = len(wolf_moves(w2, s2))
            err1 = 0
            tot = 0
            for sf, st in sheep_moves(w2, s2):
                w3, s3 = apply_sheep_move(w2, s2, sf, st)
                v = endgame.lookup(w3, s3, WOLF)
                tot += 1
                if v == WOLF_WIN:
                    err1 += 1
            rows.append(dict(cap=cap, fcaps=fcaps, mob=mob,
                             err1r=(err1 / tot if tot else 0.0)))
    return rows


def bucket_report(rows, key, buckets, label):
    print(f"\n[{label}] 按 {key} 分桶")
    acc = defaultdict(lambda: [0, 0.0, 0.0])
    for r in rows:
        b = None
        for lo, hi in buckets:
            if lo <= r[key] <= hi:
                b = (lo, hi)
                break
        if b is None:
            b = (buckets[-1][1] + 1, 999)
        acc[b][0] += 1
        acc[b][1] += r["err1r"]
        if "uniq" in r:
            acc[b][2] += 1 if r["uniq"] else 0
    for b in sorted(acc):
        n, e, u = acc[b]
        line = f"  {key} in {b}: n={n:>6}  平均一步失误率={e/n:.3f}"
        if "uniq" in rows[0]:
            line += f"  唯一和棋应手占比={u/n:.3f}"
        print(line)


def sheep_side_depth2(n_target=800):
    """深度2研究(羊方视角):羊走完后(狼走,和棋局面),对狼的每个"不败应手"R,
    计算 R 局面里狼的"一步失误率"(深度2)。指标:
      d2min = 所有不败R中再失误率的最小值(存在安全脱险路→陷阱不硬)
      d2avg = 平均值
      chain = 连续"唯一不败应手"长度(狼被迫精确应手的步数)
    分桶对比 中四角/狼机动性/安全白吃数。"""
    rows = []
    trials = 0
    while len(rows) < n_target and trials < 400000:
        trials += 1
        k = rng.choice([5, 6, 7, 8, 9, 10])
        cells = rng.sample(range(25), 3 + k)
        w = sum(1 << c for c in cells[:3])
        s = sum(1 << c for c in cells[3:])
        if endgame.lookup(w, s, SHEEP) != DRAW:
            continue
        for frm, to in sheep_moves(w, s):
            w2, s2 = apply_sheep_move(w, s, frm, to)
            if endgame.lookup(w2, s2, WOLF) != DRAW:
                continue
            safe = 0
            mob = len(wolf_moves(w2, s2))
            cent = popcount(s2 & sum(1 << c for c in CENTER))
            err1 = 0
            tot = 0
            replies = []          # (狼不败应手后的局面)
            for wf, wt, cap in wolf_moves(w2, s2):
                w3, s3 = apply_wolf_move(w2, s2, wf, wt)
                if popcount(s3) <= 3:
                    continue      # 直接吃胜不算
                v = endgame.lookup(w3, s3, SHEEP)
                tot += 1
                if v == SHEEP_WIN:
                    err1 += 1
                elif v == DRAW:
                    replies.append((w3, s3))
                    if endgame.lookup(w3, s3, WOLF) != SHEEP_WIN:
                        pass
            if tot == 0:
                continue
            # 深度2:对每个不败应手R,统计R局面(狼走)的狼一步失误率
            d2_list = []
            chain = 0
            cur_w, cur_s = w2, s2
            for _ in range(3):    # 追踪最多3步唯一应手链
                n_draw = 0
                n_win = 0
                for wf, wt, cap in wolf_moves(cur_w, cur_s):
                    w3, s3 = apply_wolf_move(cur_w, cur_s, wf, wt)
                    if popcount(s3) <= 3:
                        n_win += 1
                        continue
                    v = endgame.lookup(w3, s3, SHEEP)
                    if v == WOLF_WIN:
                        n_win += 1
                    elif v == DRAW:
                        n_draw += 1
                        keep = (w3, s3)
                if n_win == 0 and n_draw == 1:
                    chain += 1
                    cur_w, cur_s = keep
                else:
                    break
            for (w3, s3) in replies:
                e = 0
                t2 = 0
                for wf, wt, cap in wolf_moves(w3, s3):
                    w4, s4 = apply_wolf_move(w3, s3, wf, wt)
                    if popcount(s4) <= 3:
                        continue
                    if endgame.lookup(w4, s4, SHEEP) == SHEEP_WIN:
                        e += 1
                    t2 += 1
                d2_list.append(e / t2 if t2 else 0.0)
            rows.append(dict(safe=safe, mob=mob, cent=cent,
                             err1r=err1 / tot,
                             d2min=min(d2_list) if d2_list else 0.0,
                             d2avg=sum(d2_list) / len(d2_list)
                             if d2_list else 0.0,
                             chain=chain))
    return rows


def bucket_report_d2(rows, key, buckets, label):
    print(f"\n[{label}] 按 {key} 分桶(深度2)")
    acc = defaultdict(lambda: [0, 0.0, 0.0, 0.0])
    for r in rows:
        b = None
        for lo, hi in buckets:
            if lo <= r[key] <= hi:
                b = (lo, hi)
                break
        if b is None:
            b = (buckets[-1][1] + 1, 999)
        acc[b][0] += 1
        acc[b][1] += r["d2min"]
        acc[b][2] += r["d2avg"]
        acc[b][3] += r["chain"]
    for b in sorted(acc):
        n, mn, av, ch = acc[b]
        print(f"  {key} in {b}: n={n:>6}  d2min={mn/n:.3f}  d2avg={av/n:.3f}  "
              f"唯一应手链均长={ch/n:.2f}")


def main():
    print("=== 羊方视角(羊走完,狼应对)===")
    srows = sheep_side_sample(1500)
    print(f"样本(羊的后继和棋局面): {len(srows)}")
    bucket_report(srows, "safe", [(0, 0), (1, 1), (2, 2), (3, 999)], "狼安全白吃数")
    bucket_report(srows, "mob", [(0, 1), (2, 2), (3, 3), (4, 4), (5, 999)], "狼机动性")
    bucket_report(srows, "cent", [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4)], "羊占中四角数")
    bucket_report(srows, "poison", [(0, 0), (1, 1), (2, 999)], "毒吃数")

    print("\n=== 狼方视角(狼走完,羊应对)===")
    wrows = wolf_side_sample(1500)
    print(f"样本(狼的后继和棋局面): {len(wrows)}")
    caps = [r for r in wrows if r["cap"]]
    nocaps = [r for r in wrows if not r["cap"]]
    if caps and nocaps:
        print(f"  吃子: n={len(caps)} 羊一步失误率={sum(r['err1r'] for r in caps)/len(caps):.3f}"
              f" 后继可吃数均值={sum(r['fcaps'] for r in caps)/len(caps):.2f}")
        print(f"  不吃: n={len(nocaps)} 羊一步失误率={sum(r['err1r'] for r in nocaps)/len(nocaps):.3f}"
              f" 后继可吃数均值={sum(r['fcaps'] for r in nocaps)/len(nocaps):.2f}")
    bucket_report(wrows, "fcaps", [(0, 0), (1, 1), (2, 2), (3, 999)], "后继可吃招数")
    bucket_report(wrows, "mob", [(0, 1), (2, 2), (3, 3), (4, 4), (5, 999)], "狼机动性")

    print("\n=== 深度2研究(羊方视角:连环陷阱/唯一应手链)===")
    d2rows = sheep_side_depth2(800)
    print(f"样本(羊的后继和棋局面): {len(d2rows)}")
    bucket_report_d2(d2rows, "safe", [(0, 0), (1, 1), (2, 2), (3, 999)], "狼安全白吃数")
    bucket_report_d2(d2rows, "mob", [(0, 1), (2, 2), (3, 3), (4, 4), (5, 999)], "狼机动性")
    bucket_report_d2(d2rows, "cent", [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4)], "羊占中四角数")


if __name__ == "__main__":
    main()

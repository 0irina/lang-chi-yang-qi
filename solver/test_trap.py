# -*- coding: utf-8 -*-
"""陷阱功能测试:
  A) 陷阱模式:羊在和棋局面优先选"狼安全应手最少"的招法;
  B) 陷阱扫描器 find_trap:输出链合法、交替,链上狼的每一步都是该局面唯一安全应手。
"""
import random
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, wolf_moves,
                   sheep_moves, apply_wolf_move, apply_sheep_move, popcount)
import endgame
from engine import Engine

eng = Engine()
rng = random.Random(21)
fail = 0


def check(name, cond, detail=""):
    global fail
    if not cond:
        fail += 1
    print(("[OK ] " if cond else "[FAIL] ") + name + (f" {detail}" if detail else ""))


def wolf_safe_replies(w, s):
    n = 0
    for frm, to, cap in wolf_moves(w, s):
        w2, s2 = apply_wolf_move(w, s, frm, to)
        if popcount(s2) <= 3 or endgame.lookup(w2, s2, SHEEP) != SHEEP_WIN:
            n += 1
    return n


# ---- A) 陷阱模式选招 ----
eng.trap_mode = True
n = 0
bad = 0
trials = 0
while n < 150 and trials < 300000:
    trials += 1
    k = rng.choice([4, 5, 6, 7, 8])
    cells = rng.sample(range(25), 3 + k)
    w = sum(1 << c for c in cells[:3])
    s = sum(1 << c for c in cells[3:])
    if endgame.lookup(w, s, SHEEP) != DRAW:
        continue
    n += 1
    mv, info = eng.best_move(w, s, SHEEP, history=())
    w2, s2 = apply_sheep_move(w, s, mv[0], mv[1])
    got = wolf_safe_replies(w2, s2)
    b, t = eng._opp_err(w2, s2, WOLF)
    got_ratio = b / t if t else 0.0
    best_safe = 999
    best_ratio = -1.0
    for frm, to in sheep_moves(w, s):
        ww, ss = apply_sheep_move(w, s, frm, to)
        if endgame.lookup(ww, ss, WOLF) != DRAW:
            continue
        sc = wolf_safe_replies(ww, ss)
        bb, tt = eng._opp_err(ww, ss, WOLF)
        r = bb / tt if tt else 0.0
        if sc < best_safe:
            best_safe = sc
            best_ratio = r
        elif sc == best_safe and r > best_ratio:
            best_ratio = r
    if got != best_safe or got_ratio + 1e-9 < best_ratio:
        bad += 1
        if bad <= 3:
            print(f"  [陷阱模式] got safe={got} ratio={got_ratio:.3f} "
                  f"best safe={best_safe} ratio={best_ratio:.3f}")
check(f"陷阱模式选招:狼安全应手最少优先 ({n}例, 失败{bad})", bad == 0)
eng.trap_mode = False

# ---- B) 陷阱扫描器 ----
n = 0
bad = 0
trials = 0
while n < 120 and trials < 300000:
    trials += 1
    k = rng.choice([4, 5, 6, 7, 8])
    cells = rng.sample(range(25), 3 + k)
    w = sum(1 << c for c in cells[:3])
    s = sum(1 << c for c in cells[3:])
    if endgame.lookup(w, s, SHEEP) != DRAW:
        continue
    n += 1
    first, chain, desc = eng.find_trap(w, s)
    if not chain:
        continue  # 无陷阱的局面允许为空
    # 合法性 + 交替 + 唯一应手校验
    cw, cs, ct = w, s, SHEEP
    for i, (nm, a, b, cp) in enumerate(chain):
        expect = "羊" if i % 2 == 0 else "狼"
        if nm != expect:
            bad += 1
            print(f"  [扫描] 交替错误: {chain[:4]}")
            break
        if ct == SHEEP:
            if not any((m[0] == a and m[1] == b) for m in sheep_moves(cw, cs)):
                bad += 1
                break
            cw, cs = apply_sheep_move(cw, cs, a, b)
            ct = WOLF
        else:
            if not any((m[0] == a and m[1] == b and m[2] == cp)
                       for m in wolf_moves(cw, cs)):
                bad += 1
                break
            # 狼这步必须是该局面唯一安全应手
            safe = [m for m in wolf_moves(cw, cs)
                    if (lambda w3, s3: popcount(s3) <= 3 or
                        endgame.lookup(w3, s3, SHEEP) != SHEEP_WIN)(
                        *apply_wolf_move(cw, cs, m[0], m[1]))]
            if len(safe) != 1:
                bad += 1
                print(f"  [扫描] 狼应手非唯一: safe={len(safe)}")
                break
            cw, cs = apply_wolf_move(cw, cs, a, b)
            ct = SHEEP
check(f"陷阱扫描器输出链合法且狼步唯一 ({n}例, 失败{bad})", bad == 0)

print("RESULT:", "ALL OK" if fail == 0 else f"{fail} FAILURES")

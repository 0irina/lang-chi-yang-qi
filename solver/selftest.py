# -*- coding: utf-8 -*-
"""引擎冒烟测试"""
import rules
from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, ONGOING,
                   INIT_WOLVES, INIT_SHEEP, popcount, wolf_moves, sheep_moves,
                   apply_wolf_move, pos_name)
import endgame
from engine import Engine

eng = Engine()
print("已加载破解层:", eng.table_k)

# 1) 狼被围死局面(羊回合):羊应走一步把狼围死,距终局 1
W = (1 << 0) | (1 << 1) | (1 << 5)
S = (1 << 2) | (1 << 6) | (1 << 10)
v = endgame.lookup(W, S, WOLF)
print("\n围死局面 狼回合判定:", v, "应为羊胜")
# 羊回合的同局面:羊能否一步走成围死?
# 该局面羊回合:羊有走法(如 (0,2)->(0,3));走后狼仍有路。先看表值
v2 = endgame.lookup(W, S, SHEEP)
print("围死局面 羊回合判定:", v2, "距离:", endgame.lookup_dist(W, S, SHEEP))
mv, info = eng.best_move(W, S, SHEEP, ())
print("羊最佳:", mv, "info:", {k: v for k, v in info.items() if k != 'pv'})
print("PV:", info.get("pv"))

# 2) 羊剩3只局面(新规则:终局狼胜,距离 0)
W3 = (1 << 1) | (1 << 2) | (1 << 3)
S3 = (1 << 11) | (1 << 20) | (1 << 24)
mv, info = eng.best_move(W3, S3, WOLF, ())
print("\n吃子局面 狼最佳:", mv, "判定:", info["value"], "距离:", info["dist"])

# 3) 5羊随机局面:表覆盖,能出招+距离+PV
import random
rng = random.Random(7)
cells = rng.sample(range(25), 3)
W4 = sum(1 << p for p in cells)
free = [p for p in range(25) if not ((W4 >> p) & 1)]
S4 = sum(1 << p for p in rng.sample(free, 5))
mv, info = eng.best_move(W4, S4, WOLF, ())
print("\n5羊局面:", bin(W4), bin(S4))
print("判定:", info["value"], "距离:", info["dist"], "最佳:", mv)
print("PV:", info["pv"])

# 4) 初始局面(15羊,未破解层):alpha-beta 搜索(深度3快速验证)
print("\n初始局面搜索(深度3)...")
mv, info = eng.best_move(INIT_WOLVES, INIT_SHEEP, WOLF, (), depth=3)
print("最佳:", mv, "score:", info.get("score"), "nodes:", info.get("nodes"), "time:", info.get("time"))

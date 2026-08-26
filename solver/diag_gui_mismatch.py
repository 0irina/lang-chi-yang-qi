# -*- coding: utf-8 -*-
"""复现"分析箭头与候选面板第一手不一致":狼开局走败着 → 羊胜局面。"""
import os
import sys

sys.path.insert(0, r"D:\狼吃羊棋\solver")

import tkinter as tk

import gui as G
from rules import INIT_WOLVES, INIT_SHEEP, apply_wolf_move, SHEEP, pos_name

root = tk.Tk()
root.geometry("+20000+20000")
game = G.Game(root)
game.ai_wolf = False
game.ai_sheep = False
game.analysis = True
root.update()

# 狼开局败着 B5→B4 (pos 1 -> 6)
w, s = apply_wolf_move(INIT_WOLVES, INIT_SHEEP, 1, 6)
game._commit(w, s, mv=(1, 6))
game._refresh_panels()

v = __import__('endgame').lookup(game.wolves, game.sheep, SHEEP)
print(f"局面值: {v}  候选首: {pos_name(game._cand_cache[0][0])}→"
      f"{pos_name(game._cand_cache[0][1])}")
print(f"pv_moves[0]: {pos_name(game.pv_moves[0][0])}→"
      f"{pos_name(game.pv_moves[0][1])}")
if game.pv_moves[0][:2] != game._cand_cache[0][:2]:
    print("不一致!")
else:
    print("一致")
root.destroy()

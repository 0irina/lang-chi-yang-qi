# -*- coding: utf-8 -*-
"""无界面复现"变招后AI失效"bug: 人类执狼 vs AI执羊,变招驱动测试。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk

import gui as G


def pump(root, secs):
    root.after(int(secs * 1000), root.quit)
    root.mainloop()


root = tk.Tk()
root.withdraw()
game = G.Game(root)
game.ai_sheep = True  # AI执羊,人类执狼

# 诊断探针
_orig_start = game.start_ai
_orig_apply = game.apply_ai_move
_orig_fail = game.ai_failed


def dbg_start(turn):
    print(f"  [probe] start_ai({turn}) 主线程={__import__('threading').current_thread().name}")
    _orig_start(turn)


def dbg_apply(mv, info, ep=None):
    print(f"  [probe] apply_ai_move({mv})")
    _orig_apply(mv, info, ep)


def dbg_fail():
    print("  [probe] ai_failed!")
    _orig_fail()


game.start_ai = dbg_start
game.apply_ai_move = dbg_apply
game.ai_failed = dbg_fail

# 人类狼走中心吃羊(2,12)
assert game.try_move_wolf(2, 12), "首步应合法"
print("人类走了 (2,12), 等AI羊应招...")
pump(root, 6)
import threading
print("活动线程:", [t.name for t in threading.enumerate()])
print(f"move_count={game.move_count} ai_thinking={game.ai_thinking} "
      f"羊数={G.popcount(game.sheep)} history_len={len(game.history)}")

# 点变招(prev=羊=AI)
game.on_variant()
pump(root, 3)
print(f"变招后 move_count={game.move_count} ai_thinking={game.ai_thinking} "
      f"最后一步={game.last_move}")

# 再点一次变招
game.on_variant()
pump(root, 3)
print(f"二次变招后 move_count={game.move_count} ai_thinking={game.ai_thinking} "
      f"最后一步={game.last_move}")

# 人类再走一步,看AI是否还能自动应招
wm = G.wolf_moves(game.wolves, game.sheep)
if wm:
    frm, to, cap = wm[0]
    ok = game.try_move_wolf(frm, to)
    print(f"人类走 ({frm},{to}) 合法={ok}")
    pump(root, 6)
    print(f"之后 move_count={game.move_count} ai_thinking={game.ai_thinking} "
          f"(期望: AI已应招, move_count+1)")
else:
    print("狼无路可走")

# 悔棋按钮(AI对局,AI已应招)应退两步
mc_before = game.move_count
game.undo()
pump(root, 2)
print(f"AI对局悔棋: {mc_before} -> {game.move_count} "
      f"(期望退2步={mc_before-2}) 最后一步={game.last_move}")

# 纯人模式(无AI):悔棋只退一步
game.ai_sheep = False
game.restart()
pump(root, 2)
game.try_move_wolf(2, 12)
pump(root, 1)
sm = G.sheep_moves(game.wolves, game.sheep)
if sm:
    game.try_move_sheep(sm[0][0], sm[0][1])
mc_before = game.move_count
game.undo()
pump(root, 1)
print(f"纯人模式悔棋: {mc_before} -> {game.move_count} "
      f"(期望退1步={mc_before-1})")

root.destroy()
print("RESULT: DONE")

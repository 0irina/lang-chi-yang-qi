# -*- coding: utf-8 -*-
"""GUI 冒烟测试:构建界面、跑一次 AI 走子、关闭"""
import tkinter as tk
import time

import gui

root = tk.Tk()
root.withdraw()
g = gui.Game(root)
root.update()
print("GUI 构建 OK, table_k =", g.engine.table_k)

# 开启 AI 执狼,让 AI 走第一步(后台线程)
g.toggle_ai('wolf')
g.update_auto()
for _ in range(60):
    root.update()
    time.sleep(0.1)
    if not g.ai_thinking and g.move_count > 0:
        break
print("AI 走完一步, move_count =", g.move_count)
print("当前狼位:", bin(g.wolves), "羊位:", bin(g.sheep))
print("状态:", g.status_label.cget("text"))

# 玩家走一步羊(选中+落子)
g.selected = 10  # (2,1) 是羊
ok = g.try_move_sheep(10, 5)
print("羊 (3,1)->(2,1) 走子:", ok, " move_count =", g.move_count)

g.toggle_ai('wolf')  # 关掉 AI
root.destroy()
print("GUI 冒烟测试通过")

# -*- coding: utf-8 -*-
"""GUI 无头冒烟测试(需要桌面环境):验证本轮新增交互不抛异常、逻辑正确——
候选面板悬停预览箭头 / 棋谱悬停高亮 / 点击棋谱跳回并截断 / 导出棋谱。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk

import gui as G
from rules import INIT_WOLVES, INIT_SHEEP, apply_wolf_move, apply_sheep_move


class Ev:
    def __init__(self, x, y):
        self.x, self.y = x, y


root = tk.Tk()
root.geometry("+20000+20000")  # 移出屏幕外但不 withdraw,保证布局真实计算
game = G.Game(root)
game.ai_wolf = False
game.ai_sheep = False
root.update()  # 强制布局计算,Listbox 的 @x,y 行号映射才有效
game.hist_list.config(height=10)   # 给列表显式高度,行号映射更稳定
game.cand_list.config(height=12)
root.update()

# 初始局面 -> 狼 C5→C3 吃,羊 A3→A4;棋谱应有 2 步
w, s = INIT_WOLVES, INIT_SHEEP
w, s = apply_wolf_move(w, s, 2, 12)
game._commit(w, s, mv=(2, 12))
game._commit(*apply_sheep_move(w, s, 10, 5), mv=(10, 5))
assert game.move_count == 2 and len(game.history) == 2
game._refresh_panels()
assert len(game._cand_cache) > 0, "候选面板应为当前方生成候选"

# 1) 候选悬停 -> 预览箭头出现;离开 -> 清除
game.on_cand_hover(Ev(8, 8))
assert game.hover_mv is not None, "悬停候选应产生预览箭头"
assert game.hover_mv[:2] == game._cand_cache[0][:2]
game._clear_hover()
assert game.hover_mv is None

# 2) 棋谱悬停 -> 行高亮
game.on_hist_hover(Ev(8, 8))
assert game._hover_widget is game.hist_list
assert game._hover_index == 0
game._clear_hover()
assert game._hover_widget is None

# 3) 点击棋谱第0行 -> 浏览第1步之后的局面(不截断;走新棋才截断)
game.on_hist_click(Ev(8, 8))
assert game.move_count == 1, f"move_count={game.move_count}"
assert len(game.history) == 2, "浏览模式不应截断历史"
assert game.browse_target == 1
assert game.wolves == apply_wolf_move(INIT_WOLVES, INIT_SHEEP, 2, 12)[0]

# 3a) 浏览局面走与主线相同的棋 -> 沿主线前进,仍不截断
game.try_move_sheep(10, 5)
assert game.browse_target == 2 and len(game.history) == 2
assert game.move_count == 2

# 3b) 点第0行回到第1步后,走不同的棋 -> 截断开新分支
game.on_hist_click(Ev(8, 8))
game.try_move_sheep(13, 8)
assert game.browse_target is None
assert len(game.history) == 2 and game.move_count == 2
assert game.notation[1].startswith("羊 D3→D4"), game.notation

# 3c) 进入浏览后点最后一行 = 退出浏览回到最新局面
game.on_hist_click(Ev(8, 8))          # 浏览第1步后
assert game.browse_target == 1 and game.move_count == 1
game.on_hist_click(Ev(8, 26))         # 最后一行(第2行) = 退出浏览
assert game.browse_target is None and game.move_count == 2
game._refresh_panels()
assert len(game._cand_cache) > 0

# 4) 导出棋谱(接管对话框,走真实 handler 全流程)
from tkinter import filedialog, messagebox
tmp = os.path.join(tempfile.gettempdir(), "wysy_export_test.txt")
filedialog.asksaveasfilename = lambda **k: tmp
messagebox.showinfo = lambda *a, **k: None
game.on_export()
with open(tmp, "r", encoding="utf-8") as f:
    txt = f.read()
assert "1. 狼 C5→C3 吃" in txt, txt
assert "先手: 狼" in txt and "结果: 对局进行中" in txt
os.remove(tmp)

# 5) 开局库面板:书内局面(1.C5→C3 2.B3→B4 3.D5→D3)列出高压走廊走法,
#    悬停产生预览箭头
game.restart()
w, s = INIT_WOLVES, INIT_SHEEP
w, s = apply_wolf_move(w, s, 2, 12)
game._commit(w, s, mv=(2, 12))
w, s = apply_sheep_move(w, s, 11, 6)
game._commit(w, s, mv=(11, 6))
w, s = apply_wolf_move(w, s, 3, 13)
game._commit(w, s, mv=(3, 13))
game._refresh_panels()
assert len(game._book_cache) > 0, "书内局面应列出开局库走法"
assert game.book_list.size() == len(game._book_cache)
game.on_book_hover(Ev(8, 8))
assert game.hover_mv is not None, "开局库悬停应产生预览箭头"
assert game.hover_mv[:2] == game._book_cache[0][:2]
game._clear_hover()
assert game.hover_mv is None

# 5b) 高压招法面板:书内局面的书内走法应出现在"走后对方唯一正招"栏
assert game.press_list.size() >= 1, "高压招法面板应有内容"
assert len(game._press_cache) >= 1
game.on_press_hover(Ev(8, 8))
assert game.hover_mv is not None, "高压招法悬停应产生预览箭头"
game._clear_hover()
assert game.hover_mv is None

# 5c) 已定局面:分析箭头(数据层)与候选面板第一手必须一致
game.restart()
game.analysis = True                     # _refresh_analysis_now 需要分析开启
w, s = apply_wolf_move(INIT_WOLVES, INIT_SHEEP, 1, 6)   # 狼开局败着 B5→B4
game._commit(w, s, mv=(1, 6))
game._refresh_panels()
game._refresh_analysis_now()             # 同步计算分析箭头(与 GUI 同一数据路径)
assert len(game._cand_cache) > 0, "已定局面候选面板应有内容"
assert game.pv_moves, "已定局面应计算出分析箭头"
assert game.pv_moves[0][:2] == game._cand_cache[0][:2], \
    f"箭头与候选不一致: {game.pv_moves[0]} vs {game._cand_cache[0]}"

root.destroy()
print("GUI SMOKE OK")

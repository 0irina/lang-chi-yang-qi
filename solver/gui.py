# -*- coding: utf-8 -*-
"""狼吃羊棋 GUI —— 接入破解引擎

- 点击选子再点击目标格走棋
- AI执狼 / AI执羊 可开关,AI 在后台线程思考
- 状态栏实时显示当前局面判定(狼必胜/羊必胜/和棋/未破解·搜索)
- 分析区显示最佳招法与破解线(表覆盖时是严格最优线,含最快取胜步数)
- 和棋局面自动采用"不重复"的次优变招,保证棋局能继续
"""
import os
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext

import rules
from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, ONGOING,
                   INIT_WOLVES, INIT_SHEEP, popcount, wolf_moves, sheep_moves,
                   apply_wolf_move, apply_sheep_move, outcome, pos_name, WIN_NAMES)
import endgame
import tabpack
import winrate
from engine import Engine, OPENING_BOOK, OPENING_BOOK2

# ---- 界面配色(参考 chess.com / lichess 现代棋类UI:深色界面+木质棋盘) ----
BG = '#20242E'          # 窗口背景
PANEL = '#262B37'       # 面板/列表背景
PANEL_FG = '#D8DCE6'    # 面板文字
SUB_FG = '#9FB3C8'      # 次要文字(标题/坐标)
ACCENT = '#4A90D9'      # 强调蓝(选中)
BOARD_LIGHT = '#EFD9B4'  # 棋盘浅格(木质)
BOARD_DARK = '#C08A5B'   # 棋盘深格(木质)
BOARD_FRAME = '#14171E'  # 棋盘外框
LAST_HL = '#E53935'      # 最后一步四角括号(红色,醒目)
MOVE_LINE = '#E4572E'    # 最后一步虚线
SEL_EDGE = '#3FA24C'     # 选中绿色
BTN_BG = '#2E3546'
BTN_FG = '#E8EAF0'
BTN_ON = '#3D7A46'       # 开关按钮"开"状态
BO = 80                  # 棋盘原点偏移(四周留出坐标标注边距)


class Game:
    def __init__(self, root):
        self.root = root
        self.root.title("狼吃羊棋 · 破解引擎")
        self.root.geometry("1090x900")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)

        self.wolves = INIT_WOLVES
        self.sheep = INIT_SHEEP
        self.move_count = 0
        self.ai_wolf = False
        self.ai_sheep = False
        self.analysis = False
        self.selected = None
        self.history = []          # [(wolves, sheep, move_count)]
        self.pos_history = [(INIT_WOLVES, INIT_SHEEP)]  # 局面历史(重复回避)
        self.game_over = False
        self.ai_thinking = False
        self.flip = False  # 棋盘 180° 翻转
        self.last_move = None       # (frm, to) 最后一步,虚线显示
        self.analy_wolf_mv = None   # 兼容保留
        self.analy_sheep_mv = None  # 兼容保留
        self.pv_moves = []          # 分析箭头链:[(frm,to,cap), ...] 双方交替
        self.move_limit = 150       # 和棋步数上限(可调)
        self._last_analy_key = None
        self.editing = False        # 棋盘编辑模式
        self.turn_bias = 0          # 0=狼先手, 1=羊先手(编辑模式可调)
        self.start_state = (INIT_WOLVES, INIT_SHEEP, 0)  # 本局起始局面
        # 变招功能
        self.variant_n = 0          # 已点"变招"次数(局面正常变化时归零)
        self.variant_choices = []   # 当前局面同档次候选招 [(frm,to,cap),v,d]
        self._variant_key = None    # 上述候选对应的局面
        self._variant_busy = False  # 变招执行中(阻止update_auto抢跑)
        self._variant_applying = False  # 变招提交标记(commit时不重置计数)
        self.variant_override = None    # 分析模式下显示第N档变招(仅显示)
        self.epoch = 0                  # 局面代数(悔棋/变招时+1,丢弃过期的AI落子)
        self.notation = []              # 棋谱(每步文字)
        self._cand_cache = []           # 候选招法面板缓存 [(frm,to,cap),...]
        self._book_cache = []           # 开局库面板缓存 [(frm,to,cap),...]
        self._press_cache = []          # 高压招法面板缓存 [(frm,to,cap),...]
        self.hover_mv = None            # 悬停预览的招法(黄色箭头)
        self._hover_widget = None       # 当前悬停高亮的列表控件
        self._hover_index = None        # 当前悬停高亮的行号
        self.browse_target = None       # 棋谱浏览:当前查看"第N步之后"的局面
        self._browse_saved = None       # 进入浏览前的最新局面(退出浏览用)

        self.engine = Engine()
        self.engine.opening_variety = True  # 羊方开局轮换,防高手背谱
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.build_ui()
        self.update_display()
        self.update_auto()
        self._refresh_panels()
        # 常驻分析线程:AI 执子或手动开分析时,自动维护箭头链与文字分析
        threading.Thread(target=self.analysis_worker, daemon=True).start()

    def on_close(self):
        self.root.destroy()

    def _mk_btn(self, parent, text, cmd, width=9):
        b = tk.Button(parent, text=text, command=cmd, width=width,
                      font=('Microsoft YaHei UI', 10),
                      bg=BTN_BG, fg=BTN_FG,
                      activebackground='#3D4658', activeforeground='#FFFFFF',
                      relief='flat', bd=0, highlightthickness=0,
                      padx=6, pady=3, cursor='hand2')
        return b

    def _btn_state(self, btn, on):
        btn.config(bg=BTN_ON if on else BTN_BG,
                   fg='#FFFFFF' if on else BTN_FG)

    def build_ui(self):
        main = tk.Frame(self.root, bg=BG)
        main.pack(fill=tk.BOTH, expand=True)

        # 顶部:左侧棋盘+按钮栏,右侧上下三块(历史/开局库/候选招法)
        top = tk.Frame(main, bg=BG)
        top.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(6, 0))

        left = tk.Frame(top, bg=BG)
        left.pack(side=tk.LEFT, anchor=tk.N, padx=(0, 10))

        self.canvas = tk.Canvas(left, width=560, height=560, bg=BG,
                                highlightthickness=0)
        self.canvas.pack(side=tk.TOP, anchor=tk.N)
        self.canvas.bind("<Button-1>", self.on_click)

        # 按钮栏:棋盘正下方(紧凑排布)
        mode_frame = tk.Frame(left, bg=BG)
        mode_frame.pack(side=tk.TOP, pady=(2, 0))
        self.ai_wolf_btn = self._mk_btn(mode_frame, "AI执狼:关",
                                        lambda: self.toggle_ai('wolf'), 9)
        self.ai_wolf_btn.grid(row=0, column=0, padx=2, pady=2)
        self.ai_sheep_btn = self._mk_btn(mode_frame, "AI执羊:关",
                                         lambda: self.toggle_ai('sheep'), 9)
        self.ai_sheep_btn.grid(row=0, column=1, padx=2, pady=2)
        self.analysis_btn = self._mk_btn(mode_frame, "分析:关",
                                         self.toggle_analysis, 9)
        self.analysis_btn.grid(row=0, column=2, padx=2, pady=2)
        self.undo_btn = self._mk_btn(mode_frame, "悔棋", self.undo, 7)
        self.undo_btn.config(state=tk.DISABLED)
        self.undo_btn.grid(row=0, column=3, padx=2, pady=2)
        self.restart_btn = self._mk_btn(mode_frame, "重开", self.restart, 7)
        self.restart_btn.grid(row=0, column=4, padx=2, pady=2)
        self.variant_btn = self._mk_btn(mode_frame, "变招", self.on_variant, 7)
        self.variant_btn.grid(row=0, column=5, padx=2, pady=2)
        self.flip_btn = self._mk_btn(mode_frame, "翻转棋盘:关",
                                     self.toggle_flip, 11)
        self.flip_btn.grid(row=1, column=0, columnspan=2, padx=2, pady=2)
        tk.Label(mode_frame, text="和棋步数:", font=('Microsoft YaHei UI', 10),
                 fg=PANEL_FG, bg=BG).grid(
            row=1, column=2, padx=(8, 2), sticky='e')
        self.limit_var = tk.StringVar(value="150")
        self.limit_var.trace('w', self._on_limit_change)
        self.limit_spin = tk.Spinbox(mode_frame, from_=20, to=99999,
                                     increment=10, width=6,
                                     textvariable=self.limit_var,
                                     font=('Microsoft YaHei UI', 10),
                                     bg=PANEL, fg=PANEL_FG, relief='flat',
                                     insertbackground='#FFFFFF',
                                     buttonbackground=BTN_BG)
        self.limit_spin.grid(row=1, column=3, padx=2, pady=2)
        # 棋盘编辑(象棋软件式)
        self.edit_btn = self._mk_btn(mode_frame, "编辑棋盘", self.toggle_edit, 9)
        self.edit_btn.grid(row=2, column=0, padx=2, pady=2)
        self.edit_first_btn = self._mk_btn(mode_frame, "先手:狼",
                                           self.edit_toggle_first, 8)
        self.edit_clear_btn = self._mk_btn(mode_frame, "清空", self.edit_clear, 6)
        self.edit_done_btn = self._mk_btn(mode_frame, "完成", self.edit_finish, 6)
        self.edit_cancel_btn = self._mk_btn(mode_frame, "取消", self.edit_cancel, 6)
        for b in (self.edit_first_btn, self.edit_clear_btn,
                  self.edit_done_btn, self.edit_cancel_btn):
            b.grid_remove()
        self.edit_first_btn.grid(row=2, column=1, padx=2, pady=2)
        self.edit_clear_btn.grid(row=2, column=2, padx=2, pady=2)
        self.edit_done_btn.grid(row=2, column=3, padx=2, pady=2)
        self.edit_cancel_btn.grid(row=2, column=4, padx=2, pady=2)
        self._show_edit_controls(False)

        # 分析区:棋盘按钮正下方(窄栏,宽度随棋盘)
        tk.Label(left, text="分 析", font=('Microsoft YaHei UI', 11, 'bold'),
                 fg=SUB_FG, bg=BG).pack(anchor='w', pady=(6, 2))
        self.text = scrolledtext.ScrolledText(left, height=9, width=70,
                                              font=('Consolas', 10),
                                              bg=PANEL, fg=PANEL_FG,
                                              insertbackground='#FFFFFF',
                                              relief='flat', borderwidth=0)
        self.text.pack(side=tk.TOP, anchor=tk.W, pady=(0, 6))
        self.text.config(state=tk.DISABLED)

        side = tk.Frame(top, bg=BG)
        side.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        side.columnconfigure(0, weight=1)
        side.rowconfigure(1, weight=1)
        side.rowconfigure(7, weight=1)

        hist_head = tk.Frame(side, bg=BG)
        hist_head.grid(row=0, column=0, sticky='ew', pady=(0, 2))
        hist_head.columnconfigure(0, weight=1)
        tk.Label(hist_head, text="历史招法(悬停高亮·点击跳回)",
                 font=('Microsoft YaHei UI', 11, 'bold'),
                 fg=SUB_FG, bg=BG).grid(row=0, column=0, sticky='w')
        self.export_btn = self._mk_btn(hist_head, "导出棋谱", self.on_export,
                                       width=8)
        self.export_btn.grid(row=0, column=1, sticky='e')
        hist_f = tk.Frame(side, bg=BG)
        hist_f.grid(row=1, column=0, sticky='nsew', pady=(0, 10))
        hist_f.rowconfigure(0, weight=1)
        hist_f.columnconfigure(0, weight=1)
        self.hist_list = tk.Listbox(hist_f, font=('Consolas', 11), width=28,
                                    bg=PANEL, fg=PANEL_FG,
                                    selectbackground=ACCENT,
                                    selectforeground='#FFFFFF',
                                    relief='flat', highlightthickness=0,
                                    activestyle='none', exportselection=False)
        self.hist_list.grid(row=0, column=0, sticky='nsew')
        self.hist_list.bind('<Button-1>', self.on_hist_click)
        self.hist_list.bind('<Motion>', self.on_hist_hover)
        self.hist_list.bind('<Leave>', lambda e: self._clear_hover())
        hsb = tk.Scrollbar(hist_f, orient='vertical',
                           command=self.hist_list.yview)
        hsb.grid(row=0, column=1, sticky='ns')
        self.hist_list.config(yscrollcommand=hsb.set)

        tk.Label(side, text="开局库 · 高压走廊(羊走局面,点选即走)",
                 font=('Microsoft YaHei UI', 11, 'bold'), fg='#C792EA', bg=BG).grid(
            row=2, column=0, sticky='w', pady=(0, 2))
        book_f = tk.Frame(side, bg=BG)
        book_f.grid(row=3, column=0, sticky='ew', pady=(0, 6))
        book_f.columnconfigure(0, weight=1)
        self.book_list = tk.Listbox(book_f, font=('Consolas', 11), width=36,
                                    height=4, bg=PANEL, fg=PANEL_FG,
                                    selectbackground=ACCENT,
                                    selectforeground='#FFFFFF',
                                    relief='flat', highlightthickness=0,
                                    activestyle='none', exportselection=False)
        self.book_list.grid(row=0, column=0, sticky='ew')
        bsb = tk.Scrollbar(book_f, orient='vertical',
                           command=self.book_list.yview)
        bsb.grid(row=0, column=1, sticky='ns')
        self.book_list.config(yscrollcommand=bsb.set)
        self.book_list.bind('<Button-1>', self.on_book_click)
        self.book_list.bind('<Motion>', self.on_book_hover)
        self.book_list.bind('<Leave>', lambda e: self._clear_hover())

        tk.Label(side, text="高压招法 · 走后对方唯一正招(狼羊通用)",
                 font=('Microsoft YaHei UI', 11, 'bold'), fg='#F2C94C', bg=BG).grid(
            row=4, column=0, sticky='w', pady=(0, 2))
        press_f = tk.Frame(side, bg=BG)
        press_f.grid(row=5, column=0, sticky='ew', pady=(0, 6))
        press_f.columnconfigure(0, weight=1)
        self.press_list = tk.Listbox(press_f, font=('Consolas', 11), width=36,
                                     height=4, bg=PANEL, fg=PANEL_FG,
                                     selectbackground=ACCENT,
                                     selectforeground='#FFFFFF',
                                     relief='flat', highlightthickness=0,
                                     activestyle='none', exportselection=False)
        self.press_list.grid(row=0, column=0, sticky='ew')
        psb = tk.Scrollbar(press_f, orient='vertical',
                           command=self.press_list.yview)
        psb.grid(row=0, column=1, sticky='ns')
        self.press_list.config(yscrollcommand=psb.set)
        self.press_list.bind('<Button-1>', self.on_press_click)
        self.press_list.bind('<Motion>', self.on_press_hover)
        self.press_list.bind('<Leave>', lambda e: self._clear_hover())

        tk.Label(side, text="候选招法 · 玩家回合点选即走",
                 font=('Microsoft YaHei UI', 11, 'bold'), fg=SUB_FG, bg=BG).grid(
            row=6, column=0, sticky='w', pady=(0, 2))
        cand_f = tk.Frame(side, bg=BG)
        cand_f.grid(row=7, column=0, sticky='nsew')
        cand_f.rowconfigure(0, weight=1)
        cand_f.columnconfigure(0, weight=1)
        self.cand_list = tk.Listbox(cand_f, font=('Consolas', 11), width=36,
                                    bg=PANEL, fg=PANEL_FG,
                                    selectbackground=ACCENT,
                                    selectforeground='#FFFFFF',
                                    relief='flat', highlightthickness=0,
                                    activestyle='none', exportselection=False)
        self.cand_list.grid(row=0, column=0, sticky='nsew')
        csb = tk.Scrollbar(cand_f, orient='vertical',
                           command=self.cand_list.yview)
        csb.grid(row=0, column=1, sticky='ns')
        self.cand_list.config(yscrollcommand=csb.set)
        self.cand_list.bind('<Button-1>', self.on_cand_click)
        self.cand_list.bind('<Motion>', self.on_cand_hover)
        self.cand_list.bind('<Leave>', lambda e: self._clear_hover())

        ctrl = tk.Frame(main, bg=BG)
        ctrl.pack(side=tk.TOP, fill=tk.X, padx=10)

        self.status_label = tk.Label(ctrl, text="",
                                     font=('Microsoft YaHei UI', 11, 'bold'),
                                     fg='#E8EAF0', bg=BG)
        self.status_label.pack(pady=(2, 4))

    # ---------- 模式切换 ----------
    def toggle_ai(self, side):
        if side == 'wolf':
            self.ai_wolf = not self.ai_wolf
            self.ai_wolf_btn.config(text=f"AI执狼:{'开' if self.ai_wolf else '关'}")
            self._btn_state(self.ai_wolf_btn, self.ai_wolf)
        else:
            self.ai_sheep = not self.ai_sheep
            self.ai_sheep_btn.config(text=f"AI执羊:{'开' if self.ai_sheep else '关'}")
            self._btn_state(self.ai_sheep_btn, self.ai_sheep)
        self.update_auto()

    def toggle_flip(self):
        self.set_flip(not self.flip)

    def set_flip(self, value):
        self.flip = value
        self.flip_btn.config(text=f"翻转棋盘:{'开' if self.flip else '关'}")
        self._btn_state(self.flip_btn, value)
        self.update_display()

    def dpos(self, pos):
        """真实棋盘位 -> 显示位(180° 翻转)"""
        return (24 - pos) if self.flip else pos

    def cur_turn(self):
        """当前行棋方:0=狼, 1=羊(含编辑模式设定的先手偏移)"""
        return (self.move_count + self.turn_bias) % 2

    # ---------- 棋盘编辑 ----------
    def _show_edit_controls(self, show):
        for b in (self.edit_first_btn, self.edit_clear_btn,
                  self.edit_done_btn, self.edit_cancel_btn):
            if show:
                b.grid()
            else:
                b.grid_remove()

    def toggle_edit(self):
        if self.editing:
            self.edit_cancel()
        else:
            self.editing = True
            self.edit_btn.config(text="编辑中…")
            self._btn_state(self.edit_btn, True)
            self.edit_first_btn.config(text=f"先手:{'狼' if self.turn_bias == 0 else '羊'}")
            self._show_edit_controls(True)
            self.pv_moves = []
            self._last_analy_key = None
            self.ai_thinking = False
            self.update_display()

    def edit_click(self, pos):
        """点击格子循环: 空→狼→羊→空"""
        m = 1 << pos
        if (self.wolves >> pos) & 1:
            self.wolves &= ~m
            self.sheep |= m
        elif (self.sheep >> pos) & 1:
            self.sheep &= ~m
        else:
            self.wolves |= m
        self.update_display()

    def edit_clear(self):
        self.wolves = 0
        self.sheep = 0
        self.update_display()

    def edit_toggle_first(self):
        self.turn_bias = 1 - self.turn_bias
        self.edit_first_btn.config(text=f"先手:{'狼' if self.turn_bias == 0 else '羊'}")
        self.update_display()

    def edit_finish(self):
        nw = popcount(self.wolves)
        ns = popcount(self.sheep)
        if nw != 3:
            messagebox.showinfo("棋盘编辑", "狼必须恰好 3 只")
            return
        if not (3 <= ns <= 15):
            messagebox.showinfo("棋盘编辑", "羊需为 3~15 只")
            return
        self.editing = False
        self.edit_btn.config(text="编辑棋盘")
        self._btn_state(self.edit_btn, False)
        self._show_edit_controls(False)
        self.start_state = (self.wolves, self.sheep, self.turn_bias)
        self.move_count = 0
        self.selected = None
        self.history.clear()
        self.pos_history = [(self.wolves, self.sheep)]
        self.last_move = None
        self.game_over = False
        self.ai_thinking = False
        self.undo_btn.config(state=tk.DISABLED)
        self.epoch += 1
        self._reset_variants()
        self._last_analy_key = None
        self.pv_moves = []
        self.notation.clear()
        self.browse_target = None
        self._browse_saved = None
        self.update_display()
        self.check_game_over()
        self.update_auto()
        self._refresh_panels()

    def edit_cancel(self):
        self.editing = False
        self.edit_btn.config(text="编辑棋盘")
        self._btn_state(self.edit_btn, False)
        self._show_edit_controls(False)
        self.wolves, self.sheep, self.turn_bias = self.start_state
        self.move_count = 0
        self.selected = None
        self.history.clear()
        self.pos_history = [(self.wolves, self.sheep)]
        self.last_move = None
        self.game_over = False
        self.ai_thinking = False
        self.undo_btn.config(state=tk.DISABLED)
        self.epoch += 1
        self._reset_variants()
        self._last_analy_key = None
        self.pv_moves = []
        self.notation.clear()
        self.browse_target = None
        self._browse_saved = None
        self.update_display()
        self.update_auto()
        self._refresh_panels()

    # ---------- 分析 ----------
    def analysis_on(self):
        """AI 执子或手动开分析时,分析区(文字+箭头)自动启用"""
        return self.analysis or self.ai_wolf or self.ai_sheep

    def _on_limit_change(self, *a):
        try:
            v = int(self.limit_var.get())
            if v < 1:
                v = 1
            self.move_limit = v
            if getattr(self, 'status_label', None) is not None:
                self.update_display()
        except (ValueError, tk.TclError):
            pass

    def _pv_moves(self, w, s, turn, n=2, history=(), score_depth=4,
                  no_chain=True):
        """从局面 (w,s,turn) 出发的主变线:当前方最佳 -> 对方最佳应对 -> ...
        与 best_move 同一套选招(含重复回避),保证与"最佳"一致。"""
        pv = []
        try:
            budget = self.move_limit - self.move_count
            while len(pv) < n:
                if popcount(s) <= 3:
                    break
                if turn == WOLF:
                    if not wolf_moves(w, s):
                        break
                    mv, _ = self.engine.best_move(
                        w, s, WOLF, history=history, ply_budget=budget,
                        score_depth=score_depth, no_chain=no_chain)
                    if not mv or mv[0] is None:
                        break
                    frm, to, cap = mv
                    w2, s2 = apply_wolf_move(w, s, frm, to)
                else:
                    if not sheep_moves(w, s):
                        break
                    mv, _ = self.engine.best_move(
                        w, s, SHEEP, history=history, ply_budget=budget,
                        score_depth=score_depth, no_chain=no_chain)
                    if not mv or mv[0] is None:
                        break
                    frm, to, cap = mv
                    w2, s2 = apply_sheep_move(w, s, frm, to)
                pv.append((frm, to, cap))
                w, s, turn = w2, s2, 1 - turn
                budget -= 1
                if popcount(s) <= 3:
                    break
        except Exception as e:
            print(f"PV计算出错: {e}")
        return pv

    def _draw_arrow(self, frm, to, color, width=6):
        """同宽圆头箭杆 + 自绘三角箭头头(消除描边粗细不一)"""
        d1, d2 = self.dpos(frm), self.dpos(to)
        if d1 == d2:
            return
        x1 = BO + (d1 % 5) * 100
        y1 = BO + (d1 // 5) * 100
        x2 = BO + (d2 % 5) * 100
        y2 = BO + (d2 // 5) * 100
        dx, dy = x2 - x1, y2 - y1
        L = (dx * dx + dy * dy) ** 0.5
        ux, uy = dx / L, dy / L
        px, py = -uy, ux
        sx, sy = x1 + ux * 30, y1 + uy * 30        # 杆起点(离格心30)
        hx, hy = x2 - ux * 24, y2 - uy * 24        # 箭头头底边中点
        tipx, tipy = x2 + ux * 2, y2 + uy * 2      # 尖端(略过格心)
        hw = 11                                    # 箭头头半宽
        p1 = (hx + px * hw, hy + py * hw)
        p2 = (hx - px * hw, hy - py * hw)
        dark = '#14161C'
        e = 3  # 描边外扩量
        # 深色底(杆+头整体描边,头略外扩与杆底无缝衔接)
        self.canvas.create_line(sx, sy, hx, hy, fill=dark, width=width + 4,
                                capstyle='round')
        self.canvas.create_polygon(
            p1[0] + px * e - ux * e, p1[1] + py * e - uy * e,
            p2[0] - px * e - ux * e, p2[1] - py * e - uy * e,
            tipx + ux * e, tipy + uy * e,
            fill=dark, outline=dark)
        # 彩色层
        self.canvas.create_line(sx, sy, hx, hy, fill=color, width=width,
                                capstyle='round')
        self.canvas.create_polygon(p1[0], p1[1], p2[0], p2[1], tipx, tipy,
                                   fill=color, outline=color)

    def toggle_analysis(self):
        self.analysis = not self.analysis
        self.analysis_btn.config(text=f"分析:{'开' if self.analysis else '关'}")
        self._btn_state(self.analysis_btn, self.analysis)
        self._last_analy_key = None
        if self.analysis:
            self.text.config(state=tk.NORMAL)
            self.text.delete('1.0', tk.END)
            self.text.config(state=tk.DISABLED)
        else:
            self.pv_moves = []
            self.update_display()

    def analysis_worker(self):
        """常驻线程:象棋引擎式迭代加深——同一局面下深度逐层加深
        (4→10),评分与最佳招法实时刷新;每局面总预算90秒(深深度
        指数变慢,超时停在当前深度);局面变化或已定局面即停止/重算。"""
        import time
        DEPTHS = (4, 5, 6, 8)
        BUDGET = 60.0
        while True:
            try:
                if self.game_over or not self.analysis_on() or self.editing:
                    time.sleep(0.6)
                    continue
                key = (self.wolves, self.sheep, self.move_count)
                if key == self._last_analy_key:
                    time.sleep(0.6)
                    continue
                self._last_analy_key = key
                turn = (key[2] + self.turn_bias) % 2
                budget = self.move_limit - key[2]
                vv0 = endgame.lookup(key[0], key[1], turn)
                dd0 = endgame.lookup_dist(key[0], key[1], turn)
                decided = vv0 in (WOLF_WIN, SHEEP_WIN)
                n_pv = (min(dd0 + 4, 400)
                        if decided and dd0 and dd0 > 0 else 10)
                t_start = time.time()
                for dep in DEPTHS:
                    if (self.wolves, self.sheep, self.move_count) != key:
                        break
                    if time.time() - t_start > BUDGET:
                        break   # 单局面总预算,防止深深度拖太久
                    mv, info = self.engine.best_move(
                        key[0], key[1], turn, self.pos_history,
                        max_len=10, ply_budget=budget, score_depth=dep)
                    pv = self._pv_moves(key[0], key[1], turn,
                                        n=n_pv, history=self.pos_history,
                                        score_depth=dep)
                    var_n = self.variant_override
                    if var_n and var_n > 0 and not decided:
                        # 变招仅在和棋局面有意义(已定局面显示最快胜着)
                        choices = self._get_variant_choices(key[0], key[1],
                                                            turn)
                        if choices:
                            i = var_n % len(choices)
                            (frm, to, cap), vv, dd = choices[i]
                            if turn == WOLF:
                                wv, sv = apply_wolf_move(key[0], key[1],
                                                         frm, to)
                            else:
                                wv, sv = apply_sheep_move(key[0], key[1],
                                                          frm, to)
                            n_v = (min(dd + 2, 400)
                                   if vv in (WOLF_WIN, SHEEP_WIN) else 10)
                            pv = [(frm, to, cap)] + self._pv_moves(
                                wv, sv, 1 - turn, history=self.pos_history,
                                n=n_v, score_depth=dep)
                            mv, info = (frm, to, cap), dict(value=vv, dist=dd)
                    self.root.after(0, lambda k=key, t=turn, m=mv, i2=info,
                                    p=pv, vn=var_n, d=dep:
                                    self._set_analysis(k, t, m, i2, p, vn, d))
                    if decided:
                        break   # 已定局面:表值精确,无需更深
                    time.sleep(0.05)
            except RuntimeError:
                break  # 窗口已关闭
            except Exception as e:
                print(f"分析出错: {e}")
            time.sleep(1.0)

    def _set_analysis(self, key, turn, mv, info, pv, variant_n=None,
                      depth=0):
        # 竞态防护:局面已变化(走了新棋/悔棋/浏览)则丢弃过期分析结果
        if key != self._last_analy_key:
            return
        self.pv_moves = pv or []
        self.update_analysis_text(key, turn, mv, info, self.pv_moves,
                                  variant_n, depth)
        self.update_display()

    def update_analysis_text(self, key, turn, mv, info, pv, variant_n=None,
                             depth=0):
        self.text.config(state=tk.NORMAL)
        self.text.delete('1.0', tk.END)
        k = popcount(key[1])
        v = endgame.lookup(key[0], key[1], turn)
        vn = WIN_NAMES.get(v, '未破解(羊数>%d)' % self.engine.table_k)
        if v == DRAW:
            vn += "(限步判狼胜)"
        self.text.insert(tk.END, f"局面判定: {vn}\n")
        # 局面评分 + 预估胜率(人类失误模型;双AI对局只显示表值)
        if not (self.ai_wolf and self.ai_sheep):
            try:
                sc, pw, ps2, pd2 = winrate.score_position(
                    key[0], key[1], turn, eng=self.engine, depth=4)
                if v == WOLF_WIN or v == SHEEP_WIN:
                    d0 = endgame.lookup_dist(key[0], key[1], turn)
                    tag = (f"狼胜,{d0}步内" if v == WOLF_WIN
                           else f"羊胜,{d0}步内")
                elif sc > 20:
                    tag = "和棋,狼方实际占优"
                elif sc < -20:
                    tag = "和棋,羊方实际占优"
                else:
                    tag = "和棋,均势"
                self.text.insert(tk.END,
                                 f"局面评分: {sc:+.0f}({tag})\n")
                self.text.insert(
                    tk.END,
                    f"预估胜率: 狼 {pw*100:.0f}% · 和棋 {pd2*100:.0f}% · "
                    f"羊 {ps2*100:.0f}%(对失误模型;和棋判狼胜)\n")
            except Exception as e:
                print(f"胜率估计出错: {e}")
        if mv is not None:
            frm, to, cap = mv
            who = "狼" if turn == WOLF else "羊"
            tag = "吃!" if cap else ""
            head = f"变招{variant_n}" if variant_n else "最佳"
            dtxt = f"(深度{depth})" if depth else ""
            self.text.insert(tk.END, f"{head}: {who} {pos_name(frm)}→{pos_name(to)} {tag} {dtxt}\n")
            rv = info.get("raw_value", info.get("value"))
            d0 = info.get("raw_dist", info.get("dist"))
            if rv in (WOLF_WIN, SHEEP_WIN):
                if d0 is not None and d0 >= 0:
                    self.text.insert(tk.END, f"距终局: {d0} 步(双方最优)\n")
                elif d0 is not None:
                    self.text.insert(tk.END,
                                     "距终局: 未知(缺少 tt\\full_dist.dat,\n"
                                     "       请把 完整版_2_距离表.zip 解压到本游戏文件夹)\n")
            # 限步附注:此路羊胜限内杀不完(选招不受影响,只是终局提醒)
            budget = self.move_limit - key[2]
            if rv == SHEEP_WIN and d0 is not None and d0 > budget:
                self.text.insert(
                    tk.END,
                    f"注: 此路羊胜需 {d0} 步 > 限内剩余 {budget} 步,"
                    "到限判狼胜(对方失误则羊可提前取胜)\n")
        if pv:
            who = turn
            parts = []
            # 必胜/必负:整条线到终局;和棋:10步预览
            show = pv if v in (WOLF_WIN, SHEEP_WIN) else pv[:10]
            for frm, to, cap in show:
                nm = "狼" if who == WOLF else "羊"
                parts.append(f"{nm} {pos_name(frm)}→{pos_name(to)}"
                             f"{'(吃)' if cap else ''}")
                who = 1 - who
            if v in (WOLF_WIN, SHEEP_WIN):
                parts.append("狼胜" if v == WOLF_WIN else "羊胜")
            self.text.insert(tk.END, "分析线: " + " / ".join(parts) + "\n")
        elif info.get("pv"):
            self.text.insert(tk.END, "破解线: " + " / ".join(info["pv"]) + "\n")
        if not info.get("table", False):
            self.text.insert(tk.END, f"[搜索评估 {info.get('score')} 分, 节点 {info.get('nodes')}]\n")
        self.text.config(state=tk.DISABLED)

    # ---------- AI 走子 ----------
    def update_auto(self):
        if self.browse_target is not None:
            return  # 浏览模式:AI 不自动走子,由玩家手动走棋
        if self.game_over or self.ai_thinking or self.editing or self._variant_busy:
            return
        if self.cur_turn() == 0:
            if self.ai_wolf:
                self.start_ai(0)
            else:
                self.status_label.config(text="轮到你走狼:点击狼,再点击目标格")
        else:
            if self.ai_sheep:
                self.start_ai(1)
            else:
                self.status_label.config(text="轮到你走羊:点击羊,再点击目标格")

    def start_ai(self, turn):
        self.ai_thinking = True
        self.status_label.config(text="AI思考中...")
        ep = self.epoch

        def calc():
            try:
                mv, info = self.engine.best_move(self.wolves, self.sheep, turn,
                                                 self.pos_history,
                                                 ply_budget=self.move_limit - self.move_count)
                try:
                    self.root.after(0, lambda: self.apply_ai_move(mv, info, ep))
                except RuntimeError:
                    pass
            except Exception as e:
                print(f"AI走棋出错: {e}")
                try:
                    self.root.after(0, self.ai_failed)
                except RuntimeError:
                    pass
        t = threading.Thread(target=calc, daemon=True)
        t.start()

    def apply_ai_move(self, mv, info, ep=None):
        if ep is not None and ep != self.epoch:
            return  # 局面已被悔棋/变招改变,丢弃过期的落子
        if mv is None:
            self.ai_failed()
            return
        frm, to, cap = mv
        if self.cur_turn() == WOLF:
            new_w, new_s = apply_wolf_move(self.wolves, self.sheep, frm, to)
        else:
            new_w, new_s = apply_sheep_move(self.wolves, self.sheep, frm, to)
        # 限步规则醒目提示(仅终局提醒,不影响选招):
        # 走完这步后表值=羊胜但限内杀不完,到限判狼胜
        rv = info.get("raw_value", info.get("value"))
        rd = info.get("raw_dist", info.get("dist"))
        if rv == SHEEP_WIN and rd is not None and rd >= 0:
            budget = self.move_limit - self.move_count
            if rd > budget:
                self.status_label.config(
                    text=f"此路羊胜需{rd}步 > 限内剩余{budget}步,到限判狼胜"
                         f"(对方失误则羊可提前取胜)")
        self._commit(new_w, new_s, (frm, to))

    def ai_failed(self):
        self.ai_thinking = False
        self.status_label.config(text="AI计算失败,请手动走棋")
        self.update_auto()

    # ---------- 走子与记录 ----------
    def _reset_variants(self):
        self.variant_n = 0
        self.variant_choices = []
        self._variant_key = None
        self.variant_override = None

    def _commit(self, new_w, new_s, mv=None):
        # 浏览模式:在旧局面走棋
        tgt = self.browse_target
        if tgt is not None:
            if tgt + 1 < len(self.history):
                same = (self.history[tgt + 1][0] == new_w and
                        self.history[tgt + 1][1] == new_s)
            else:
                # 原主线下一步通向"最新局面"(进入浏览时已保存)
                same = (self._browse_saved is not None and
                        self._browse_saved[0] == new_w and
                        self._browse_saved[1] == new_s)
            if same:
                # 与主线相同:继续浏览主线的下一局面,不新建历史
                self.browse_target = tgt + 1
                self.wolves, self.sheep = new_w, new_s
                self.move_count = tgt + 1
                self.last_move = mv
                self.selected = None
                self.update_display()
                self._set_browse_status()
                self._refresh_panels()
                return
            # 走了不同的棋:截断其后走法,从浏览局面开新分支
            del self.history[tgt:]
            del self.notation[tgt:]
            del self.pos_history[tgt + 1:]
            self.move_count = tgt
            self.browse_target = None
            self._browse_saved = None
        applying = self._variant_applying
        self._variant_applying = False
        if not applying:
            self._reset_variants()
        mover = (self.move_count + self.turn_bias) % 2
        cap = mover == WOLF and popcount(new_s) < popcount(self.sheep)
        if mv is not None:
            who = "狼" if mover == WOLF else "羊"
            self.notation.append(
                f"{who} {pos_name(mv[0])}→{pos_name(mv[1])}"
                f"{' 吃' if cap else ''}")
        self.history.append((self.wolves, self.sheep, self.move_count,
                             self.last_move))
        self.wolves, self.sheep = new_w, new_s
        self.last_move = mv
        pos = (new_w, new_s)
        self.pos_history.append(pos)
        if len(self.pos_history) > 200:
            self.pos_history = self.pos_history[-200:]
        self.move_count += 1
        self.selected = None
        self.ai_thinking = False
        self.undo_btn.config(state=tk.NORMAL)
        self.update_display()
        self.check_game_over()
        self.update_auto()
        self._refresh_panels()

    def check_game_over(self):
        if popcount(self.sheep) <= 3:
            self.game_over = True
            self.status_label.config(text="羊被吃到只剩3只,狼获胜!")
            messagebox.showinfo("游戏结束", "狼获胜!(羊只剩3只)")
        elif not wolf_moves(self.wolves, self.sheep):
            self.game_over = True
            self.status_label.config(text="狼被围死,羊获胜!")
            messagebox.showinfo("游戏结束", "羊获胜!")
        elif self.pos_history.count((self.wolves, self.sheep)) >= 5:
            self.game_over = True
            self.status_label.config(
                text="同一局面第5次出现,和棋判狼胜!")
            messagebox.showinfo("游戏结束", "同一局面第5次出现:和棋判狼胜!")
        elif self.move_count >= self.move_limit:
            self.game_over = True
            self.status_label.config(
                text=f"达到{self.move_limit}步限制,狼胜!(和棋判狼胜)")
            messagebox.showinfo("游戏结束",
                                f"{self.move_limit}步限制:和棋判狼胜!")

    def on_click(self, event):
        col = round((event.x - BO) / 100)
        row = round((event.y - BO) / 100)
        if not (0 <= row < 5 and 0 <= col < 5):
            return
        pos = row * 5 + col
        pos = self.dpos(pos)  # 翻转映射:显示位 -> 真实棋盘位
        if self.editing:
            self.edit_click(pos)
            return
        if self.game_over or self.ai_thinking:
            return
        turn = self.cur_turn()
        if turn == 0:
            if self.ai_wolf:
                return
            if (self.wolves >> pos) & 1:
                self.selected = pos
                self.update_display()
                return
            if self.selected is not None:
                if self.try_move_wolf(self.selected, pos):
                    return
                self.selected = None
                self.update_display()
        else:
            if self.ai_sheep:
                return
            if (self.sheep >> pos) & 1:
                self.selected = pos
                self.update_display()
                return
            if self.selected is not None:
                if self.try_move_sheep(self.selected, pos):
                    return
                self.selected = None
                self.update_display()

    def try_move_wolf(self, frm, to):
        dr = to // 5 - frm // 5
        dc = to % 5 - frm % 5
        empty = ~(self.wolves | self.sheep) & rules.ALL_MASK
        if abs(dr) + abs(dc) == 1 and (empty >> to) & 1:
            self._commit((self.wolves ^ (1 << frm)) | (1 << to), self.sheep,
                         (frm, to))
            return True
        if (abs(dr) == 2 and dc == 0) or (abs(dc) == 2 and dr == 0):
            mid = frm + (to - frm) // 2
            if (empty >> mid) & 1 and (self.sheep >> to) & 1:
                new_w = (self.wolves ^ (1 << frm)) | (1 << to)
                new_s = self.sheep & ~(1 << to)
                self._commit(new_w, new_s, (frm, to))
                return True
        return False

    def try_move_sheep(self, frm, to):
        dr = to // 5 - frm // 5
        dc = to % 5 - frm % 5
        empty = ~(self.wolves | self.sheep) & rules.ALL_MASK
        if abs(dr) + abs(dc) == 1 and (empty >> to) & 1:
            self._commit(self.wolves, (self.sheep ^ (1 << frm)) | (1 << to),
                         (frm, to))
            return True
        return False

    # ---------- 悔棋 / 重开 ----------
    def _undo_one(self):
        """精确退一步(不动UI状态),返回是否成功。变招流程内部使用。"""
        if not self.history:
            return False
        self.epoch += 1
        if len(self.history) == 1:
            self.wolves, self.sheep, self.turn_bias = self.start_state
            self.move_count = 0
            self.history.clear()
            self.notation.clear()
            self.pos_history = [(self.wolves, self.sheep)]
            self.last_move = None
        else:
            self.wolves, self.sheep, self.move_count, self.last_move = \
                self.history.pop()
            if self.notation:
                self.notation.pop()
            self.pos_history.pop()
        return True

    def undo(self):
        """悔棋按钮 = 撤回用户那一步:
        - 浏览模式:先退出浏览回到最新局面(不悔棋);
        - AI对局且AI已应招(通常如此,AI秒回):连退两步回到用户走之前;
        - AI对局但AI还没走(思考中):只退一步;
        - 无AI(纯人操作/分析):只退一步。"""
        if self.browse_target is not None:
            self._exit_browse()
            return
        if not self.history:
            return
        was_thinking = self.ai_thinking
        self._undo_one()
        turn = self.cur_turn()
        ai_now = (turn == WOLF and self.ai_wolf) or \
                 (turn == SHEEP and self.ai_sheep)
        if ai_now and not was_thinking and self.history:
            self._undo_one()
        self.undo_btn.config(state=tk.NORMAL if self.history else tk.DISABLED)
        self.selected = None
        self.game_over = False
        self.ai_thinking = False
        self._reset_variants()
        self._last_analy_key = None
        self.pv_moves = []
        self.update_display()
        self.update_auto()
        self._refresh_panels()

    def restart(self):
        self.wolves, self.sheep = INIT_WOLVES, INIT_SHEEP
        self.turn_bias = 0
        self.start_state = (INIT_WOLVES, INIT_SHEEP, 0)
        self.move_count = 0
        self.selected = None
        self.history.clear()
        self.pos_history = [(INIT_WOLVES, INIT_SHEEP)]
        self.last_move = None
        self.game_over = False
        self.ai_thinking = False
        self.undo_btn.config(state=tk.DISABLED)
        if self.editing:
            self.editing = False
            self.edit_btn.config(text="编辑棋盘")
            self._btn_state(self.edit_btn, False)
            self._show_edit_controls(False)
        self.epoch += 1
        self._reset_variants()
        self._last_analy_key = None
        self.pv_moves = []
        self.notation.clear()
        self.browse_target = None
        self._browse_saved = None
        self.update_display()
        self.update_auto()
        self._refresh_panels()

    # ---------- 变招 ----------
    def _get_variant_choices(self, w, s, turn):
        key = (w, s, turn)
        if key != self._variant_key or not self.variant_choices:
            budget = self.move_limit - self.move_count
            self.variant_choices = self.engine.ranked_moves(
                w, s, turn, self.pos_history, ply_budget=budget,
                score_depth=4, no_chain=True)
            self._variant_key = key
        return self.variant_choices

    def on_variant(self):
        if self.game_over or self.ai_thinking or self.editing:
            return
        try:
            turn = self.cur_turn()
            prev = 1 - turn
            prev_ai = (prev == WOLF and self.ai_wolf) or \
                      (prev == SHEEP and self.ai_sheep)
            cur_ai = (turn == WOLF and self.ai_wolf) or \
                     (turn == SHEEP and self.ai_sheep)
            if cur_ai:
                # 轮到AI走:直接换一档走
                self._variant_busy = True
                self.variant_n += 1
                self._play_variant(self.variant_n)
                return
            if prev_ai and self.history:
                # AI刚走完:只退AI那一步,换一档重走
                self._variant_busy = True
                self.variant_n += 1
                n = self.variant_n
                self._undo_one()
                self._reset_variants()
                self.variant_n = n
                self._play_variant(n)
                return
            # 无人执AI:分析模式下仅切换显示的招法
            if self.analysis:
                self.variant_n += 1
                self.variant_override = self.variant_n
                self._last_analy_key = None
                self.update_display()
        except Exception as e:
            print(f"变招出错: {e}")
        finally:
            self._variant_busy = False
            self.update_auto()

    def _play_variant(self, n):
        w, s, turn = self.wolves, self.sheep, self.cur_turn()
        choices = self._get_variant_choices(w, s, turn)
        if not choices:
            return
        (frm, to, cap), v, d = choices[n % len(choices)]
        if turn == WOLF:
            new_w, new_s = apply_wolf_move(w, s, frm, to)
        else:
            new_w, new_s = apply_sheep_move(w, s, frm, to)
        self._variant_applying = True
        self._commit(new_w, new_s, (frm, to))

    # ---------- 面板:棋谱 / 候选招法 ----------
    def _refresh_analysis_now(self):
        """同步刷新分析文字与箭头(走子后立即调用,避免与候选面板不同步)。
        先显示快速短预览;随后后台线程用完整逻辑(必胜线走到底/和棋10步)
        重算覆盖(通过把 _last_analy_key 复位来实现)。"""
        if self.game_over or self.editing or not self.analysis_on():
            return
        try:
            key = (self.wolves, self.sheep, self.move_count)
            turn = self.cur_turn()
            budget = self.move_limit - self.move_count
            mv, info = self.engine.best_move(key[0], key[1], turn,
                                             self.pos_history, max_len=10,
                                             ply_budget=budget,
                                             score_depth=4, no_chain=True)
            pv = self._pv_moves(key[0], key[1], turn,
                                history=self.pos_history, score_depth=4,
                                no_chain=True)
            self._last_analy_key = key      # 即时预览通过竞态校验
            self._set_analysis(key, turn, mv, info, pv)
            self._last_analy_key = None     # 让后台线程用迭代加深重算
        except Exception as e:
            print(f"即时分析失败: {e}")

    def _refresh_panels(self):
        """刷新棋谱与候选招法面板。候选只显示"最佳档"好棋(不败招),
        档内按引擎排序从优到次。"""
        self._clear_hover()
        self.hist_list.delete(0, tk.END)
        for i, t in enumerate(self.notation, 1):
            self.hist_list.insert(tk.END, f"{i}. {t}")
        if self.notation:
            self.hist_list.see(tk.END)
        self.cand_list.delete(0, tk.END)
        self._cand_cache = []
        self.book_list.delete(0, tk.END)
        self._book_cache = []
        if self.game_over or self.editing:
            self.book_list.insert(tk.END, "— 当前局面不在开局库 —")
            self.book_list.itemconfig(0, fg='#5A6B80')
            self.press_list.insert(tk.END, "— 无走后唯一正招的着法 —")
            self.press_list.itemconfig(0, fg='#5A6B80')
            return
        try:
            turn = self.cur_turn()
            moves = self.engine.ranked_moves(
                self.wolves, self.sheep, turn, self.pos_history,
                ply_budget=self.move_limit - self.move_count, raw=True,
                score_depth=4, no_chain=True)
        except Exception as e:
            print(f"候选面板出错: {e}")
            moves = []
        who = "狼" if turn == WOLF else "羊"
        for i, ((frm, to, cap), v, d) in enumerate(moves, 1):
            val = WIN_NAMES.get(v, "?")
            dist = f" d={d}" if (v in (WOLF_WIN, SHEEP_WIN) and d >= 0) else ""
            self.cand_list.insert(tk.END,
                                  f"{i}. {who} {pos_name(frm)}→{pos_name(to)}"
                                  f"{'吃' if cap else ''}  {val}{dist}")
            fg = ('#4ADE80' if v == WOLF_WIN else
                  ('#E4572E' if v == SHEEP_WIN else '#9FB3C8'))
            self.cand_list.itemconfig(i - 1, fg=fg)
            self._cand_cache.append((frm, to, cap))
        # 开局库面板(高压走廊):主选(深紫,狼唯一正招)+次选(浅紫,压力稍小)
        bmsg = "— 当前局面不在开局库 —"
        try:
            if self.cur_turn() == SHEEP:
                shown = []
                for book, color, tag in (
                        (OPENING_BOOK, '#C792EA', '· 高压走廊'),
                        (OPENING_BOOK2, '#DCCBEF', '· 次选高压')):
                    bm = book.get((self.wolves, self.sheep))
                    if bm:
                        for (a, b) in bm:
                            shown.append((a, b, False, color, tag))
                if shown:
                    bmsg = None
                    for (a, b, cap, color, tag) in shown:
                        self.book_list.insert(
                            tk.END, f"羊 {pos_name(a)}→{pos_name(b)} {tag}")
                        self.book_list.itemconfig(tk.END, fg=color)
                        self._book_cache.append((a, b, cap))
        except Exception:
            pass
        if bmsg is not None:
            self.book_list.insert(tk.END, bmsg)
            self.book_list.itemconfig(0, fg='#5A6B80')
        # 高压招法面板(狼羊通用):走后对方只剩唯一不败着法的着法
        self.press_list.delete(0, tk.END)
        self._press_cache = []
        pmsg = "— 无走后唯一正招的着法 —"
        try:
            if not self.game_over and not self.editing:
                turn = self.cur_turn()
                press = self._unique_reply_moves(self.wolves, self.sheep,
                                                 turn)
                if press:
                    pmsg = None
                    nm = "狼" if turn == WOLF else "羊"
                    for (a, b, cap) in press:
                        self.press_list.insert(
                            tk.END,
                            f"{nm} {pos_name(a)}→{pos_name(b)}"
                            f"{'吃' if cap else ''} · 对方唯一正招")
                        self.press_list.itemconfig(tk.END, fg='#F2C94C')
                        self._press_cache.append((a, b, cap))
        except Exception:
            pass
        if pmsg is not None:
            self.press_list.insert(tk.END, pmsg)
            self.press_list.itemconfig(0, fg='#5A6B80')
        # 同步刷新分析文字/箭头,保证与候选面板一致(消除时间差错位)
        self._refresh_analysis_now()

    def on_cand_click(self, ev):
        """玩家回合点选候选招法=自动走一步(AI回合仅查看)"""
        if self.game_over or self.editing or self.ai_thinking:
            return
        i = self.cand_list.index(f"@{ev.x},{ev.y}")
        if i is None:
            return
        try:
            i = int(i)
        except ValueError:
            return
        turn = self.cur_turn()
        if (turn == WOLF and self.ai_wolf) or (turn == SHEEP and self.ai_sheep):
            return  # AI回合:仅查看,不可点
        if 0 <= i < len(self._cand_cache):
            frm, to, cap = self._cand_cache[i]
            if turn == WOLF:
                self.try_move_wolf(frm, to)
            else:
                self.try_move_sheep(frm, to)

    def on_book_click(self, ev):
        """开局库面板点选:人类执羊回合可直接走书内高压走廊着法"""
        if self.game_over or self.editing or self.ai_thinking:
            return
        i = self.book_list.index(f"@{ev.x},{ev.y}")
        if i is None:
            return
        try:
            i = int(i)
        except ValueError:
            return
        turn = self.cur_turn()
        if turn != SHEEP or self.ai_sheep:
            return  # 仅人类执羊回合可点(AI执羊时仅查看)
        if 0 <= i < len(self._book_cache):
            frm, to, cap = self._book_cache[i]
            self.try_move_sheep(frm, to)

    def on_book_hover(self, ev):
        """开局库面板悬停:高亮该行并在棋盘画黄色预览箭头"""
        i = self.book_list.index(f"@{ev.x},{ev.y}")
        if i is None:
            return
        try:
            i = int(i)
        except ValueError:
            return
        if not (0 <= i < len(self._book_cache)):
            return
        self._hover_row(self.book_list, i)
        self.hover_mv = self._book_cache[i]
        self.update_display()

    def _unique_reply_moves(self, w, s, turn):
        """当前方走后,对方恰好只剩唯一不败着法的着法列表(狼羊通用)。"""
        out = []
        if turn == WOLF:
            for a, b, cap in wolf_moves(w, s):
                w2, s2 = apply_wolf_move(w, s, a, b)
                if popcount(s2) <= 3:
                    continue
                if endgame.lookup(w2, s2, SHEEP) != DRAW:
                    continue
                n = 0
                for sa, sb in sheep_moves(w2, s2):
                    w3, s3 = apply_sheep_move(w2, s2, sa, sb)
                    if endgame.lookup(w3, s3, WOLF) != WOLF_WIN:
                        n += 1
                if n == 1:
                    out.append((a, b, cap))
        else:
            for a, b in sheep_moves(w, s):
                w2, s2 = apply_sheep_move(w, s, a, b)
                if endgame.lookup(w2, s2, WOLF) != DRAW:
                    continue
                n = 0
                for wa, wb, cap in wolf_moves(w2, s2):
                    w3, s3 = apply_wolf_move(w2, s2, wa, wb)
                    if popcount(s3) <= 3 or \
                            endgame.lookup(w3, s3, SHEEP) == DRAW:
                        n += 1
                if n == 1:
                    out.append((a, b, False))
        return out

    def on_press_click(self, ev):
        """高压招法面板点选:人类回合可直接走该着法(AI回合仅查看)"""
        if self.game_over or self.editing or self.ai_thinking:
            return
        i = self.press_list.index(f"@{ev.x},{ev.y}")
        if i is None:
            return
        try:
            i = int(i)
        except ValueError:
            return
        turn = self.cur_turn()
        if (turn == WOLF and self.ai_wolf) or (turn == SHEEP and self.ai_sheep):
            return
        if 0 <= i < len(self._press_cache):
            frm, to, cap = self._press_cache[i]
            if turn == WOLF:
                self.try_move_wolf(frm, to)
            else:
                self.try_move_sheep(frm, to)

    def on_press_hover(self, ev):
        """高压招法面板悬停:高亮该行并在棋盘画黄色预览箭头"""
        i = self.press_list.index(f"@{ev.x},{ev.y}")
        if i is None:
            return
        try:
            i = int(i)
        except ValueError:
            return
        if not (0 <= i < len(self._press_cache)):
            return
        self._hover_row(self.press_list, i)
        self.hover_mv = self._press_cache[i]
        self.update_display()

    def _hover_row(self, widget, i):
        """高亮悬停行(仅改底色,不触发选择事件),还原上一悬停行"""
        if getattr(self, '_hover_widget', None) is not None:
            try:
                self._hover_widget.itemconfig(self._hover_index, bg=PANEL)
            except tk.TclError:
                pass
        self._hover_widget, self._hover_index = widget, i
        widget.itemconfig(i, bg='#39435A')

    def _clear_hover(self):
        """清除悬停预览(候选面板/棋谱面板共用)"""
        if getattr(self, '_hover_widget', None) is not None:
            try:
                self._hover_widget.itemconfig(self._hover_index, bg=PANEL)
            except tk.TclError:
                pass
            self._hover_widget = None
            self._hover_index = None
        if self.hover_mv is not None:
            self.hover_mv = None
            self.update_display()

    def on_cand_hover(self, ev):
        """候选面板悬停:高亮该行并在棋盘画黄色预览箭头(仅查看)"""
        i = self.cand_list.index(f"@{ev.x},{ev.y}")
        if i is None:
            return
        try:
            i = int(i)
        except ValueError:
            return
        if not (0 <= i < len(self._cand_cache)):
            return
        self._hover_row(self.cand_list, i)
        self.hover_mv = self._cand_cache[i]
        self.update_display()

    def on_hist_hover(self, ev):
        """棋谱面板悬停:高亮该行(便于随后点击跳转)"""
        i = self.hist_list.index(f"@{ev.x},{ev.y}")
        if i is None:
            return
        try:
            i = int(i)
        except ValueError:
            return
        if 0 <= i < len(self.history):
            self._hover_row(self.hist_list, i)

    def on_hist_click(self, ev):
        """点击棋谱第i行:跳转到第i+1步之后的局面【仅查看,不删除最新局面】。
        在此局面走棋:与主线相同→沿主线继续看;走不同棋→截断其后的走法开新分支。
        点击最后一行=退出浏览回到最新局面。"""
        i = self.hist_list.index(f"@{ev.x},{ev.y}")
        if i is None:
            return
        try:
            i = int(i)
        except ValueError:
            return
        target = i + 1
        if target >= len(self.history):
            self._exit_browse()      # 点最后一行 = 回到最新局面
            return
        if self.browse_target is None:
            # 首次进入浏览:保存最新局面,用于退出浏览
            self._browse_saved = (self.wolves, self.sheep,
                                  self.move_count, self.last_move)
        # history[target] = 第 target+1 步走之前的快照 = 第 i+1 步之后的局面
        self.wolves, self.sheep, self.move_count, self.last_move = \
            self.history[target]
        self.browse_target = target
        self.selected = None
        self.game_over = False
        self.ai_thinking = False
        self._reset_variants()
        self._last_analy_key = None
        self.pv_moves = []
        self._clear_hover()
        self.update_display()
        self._set_browse_status()
        self._refresh_panels()

    def _set_browse_status(self):
        self.status_label.config(
            text=f"浏览第{self.browse_target}步后的局面 · 在此走棋:同主线续看,"
                 f"不同则开新分支 · 点棋谱最后一行或悔棋=回到最新局面")

    def _exit_browse(self):
        if self.browse_target is None:
            return
        self.wolves, self.sheep, self.move_count, self.last_move = \
            self._browse_saved
        self.browse_target = None
        self._browse_saved = None
        self.selected = None
        self.game_over = False
        self.ai_thinking = False
        self._reset_variants()
        self._last_analy_key = None
        self.pv_moves = []
        self._clear_hover()
        self.update_display()
        self.update_auto()
        self._refresh_panels()

    def on_export(self):
        """导出棋谱到文本文件(UTF-8,可发给教练复盘)"""
        from tkinter import filedialog
        import datetime
        default = os.path.join(os.path.expanduser("~"), "Desktop",
                               "狼吃羊棋_棋谱.txt")
        path = filedialog.asksaveasfilename(
            title="导出棋谱", defaultextension=".txt",
            initialfile="狼吃羊棋_棋谱.txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if not path:
            return
        lines = ["狼吃羊棋 · 棋谱",
                 f"导出时间: {datetime.datetime.now():%Y-%m-%d %H:%M:%S}",
                 f"先手: {'狼' if self.turn_bias == 0 else '羊'}"
                 f" · 和棋步数限制: {self.move_limit} 步"
                 "———————————————"]
        for i, t in enumerate(self.notation, 1):
            lines.append(f"{i}. {t}")
        lines.append("———————————————")
        if self.game_over:
            lines.append(f"结果: {self.status_label.cget('text')}")
        else:
            lines.append("结果: 对局进行中")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except OSError as e:
            messagebox.showerror("导出失败", f"无法写入文件:\n{e}")
            return
        messagebox.showinfo("导出成功", f"已保存到:\n{path}")

    def toggle_trap(self):
        """羊方陷阱模式:和棋局面优先逼狼唯一安全应手"""
        self.engine.trap_mode = not self.engine.trap_mode
        self.trap_btn.config(text=f"陷阱:{'开' if self.engine.trap_mode else '关'}")
        self._btn_state(self.trap_btn, self.engine.trap_mode)
        self._last_analy_key = None
        self._refresh_panels()
        self.update_display()

    def toggle_pressure(self):
        """狼方施压模式:和棋局面优先逼羊安全应手最少(保持三角等压迫阵)"""
        self.engine.wolf_pressure = not self.engine.wolf_pressure
        self.press_btn.config(
            text=f"施压:{'开' if self.engine.wolf_pressure else '关'}")
        self._btn_state(self.press_btn, self.engine.wolf_pressure)
        self._last_analy_key = None
        self._refresh_panels()
        self.update_display()

    def on_find_trap(self):
        """陷阱扫描:找当前局面下羊的"唯一应手"压迫线,显示到分析区与箭头"""
        if self.game_over or self.editing:
            return
        if self.cur_turn() != SHEEP:
            self.text.config(state=tk.NORMAL)
            self.text.delete('1.0', tk.END)
            self.text.insert(tk.END, "陷阱扫描仅对羊走局面有意义(狼的和棋=胜,无需陷阱)\n")
            self.text.config(state=tk.DISABLED)
            return
        try:
            first, chain, desc = self.engine.find_trap(
                self.wolves, self.sheep)
        except Exception as e:
            print(f"陷阱扫描出错: {e}")
            return
        self.text.config(state=tk.NORMAL)
        self.text.delete('1.0', tk.END)
        self.text.insert(tk.END, desc + "\n")
        if chain:
            self.text.insert(tk.END, "注:狼方为该局面唯一安全应手(走别的即输)\n")
        self.text.config(state=tk.DISABLED)
        self.pv_moves = [(a, b, cp) for _, a, b, cp in chain][:2]
        self.update_display()

    # ---------- 显示 ----------
    def _draw_piece(self, d, kind, selected=False):
        x = BO + (d % 5) * 100
        y = BO + (d // 5) * 100
        # 底部阴影(点阵模拟半透明,与棋子同心,仅右下微移2px)
        self.canvas.create_oval(x - 26, y - 25, x + 28, y + 29,
                                fill='#000000', stipple='gray50', outline='')
        if kind == 'wolf':
            body, hi, edge, ch = '#474A57', '#7C7F90', '#17181E', '#F5F5F5'
        else:
            body, hi, edge, ch = '#F7F3E7', '#FFFFFF', '#8F8577', '#3A3A3A'
        if selected:
            edge = SEL_EDGE
        self.canvas.create_oval(x - 30, y - 30, x + 30, y + 30,
                                fill=body, outline=edge, width=2)
        # 左上高光
        self.canvas.create_oval(x - 22, y - 24, x + 2, y + 2,
                                fill=hi, outline='', stipple='gray25')
        self.canvas.create_text(x, y, text='狼' if kind == 'wolf' else '羊',
                                font=('Microsoft YaHei UI', 17, 'bold'),
                                fill=ch)

    def update_display(self):
        self.canvas.delete("all")
        # 棋盘格(深浅交替木质)
        for r in range(5):
            for c in range(5):
                x = BO + c * 100
                y = BO + r * 100
                col = BOARD_LIGHT if (r + c) % 2 == 0 else BOARD_DARK
                self.canvas.create_rectangle(x - 50, y - 50, x + 50, y + 50,
                                             fill=col, outline='')
        # 外框
        self.canvas.create_rectangle(BO - 48, BO - 48, BO + 448, BO + 448, outline=BOARD_FRAME,
                                     width=6)
        # 行/列坐标标注:列 A-E(左→右),行 1-5(下→上),如 C3
        for i in range(5):
            x = BO + i * 100
            real_col = 4 - i if self.flip else i
            self.canvas.create_text(x, 24, text='ABCDE'[real_col],
                                    font=('Arial', 11, 'bold'), fill=SUB_FG)
            y = BO + i * 100
            real_row = 4 - i if self.flip else i
            self.canvas.create_text(24, y, text=str(5 - real_row),
                                    font=('Arial', 11, 'bold'), fill=SUB_FG)
        # 最后一步:四角括号 + 虚线(象棋软件式)
        if self.last_move is not None:
            frm, to = self.last_move
            for p in (frm, to):
                d = self.dpos(p)
                r, c = divmod(d, 5)
                x = BO + c * 100
                y = BO + r * 100
                h, L = 36, 16
                for x1, y1, x2, y2 in (
                    (x - h, y - h, x - h + L, y - h),
                    (x - h, y - h, x - h, y - h + L),
                    (x + h, y - h, x + h - L, y - h),
                    (x + h, y - h, x + h, y - h + L),
                    (x - h, y + h, x - h + L, y + h),
                    (x - h, y + h, x - h, y + h - L),
                    (x + h, y + h, x + h - L, y + h),
                    (x + h, y + h, x + h, y + h - L),
                ):
                    self.canvas.create_line(x1, y1, x2, y2, fill=LAST_HL,
                                            width=4, capstyle='round')
            d1, d2 = self.dpos(frm), self.dpos(to)
            x1 = BO + (d1 % 5) * 100
            y1 = BO + (d1 // 5) * 100
            x2 = BO + (d2 % 5) * 100
            y2 = BO + (d2 // 5) * 100
            self.canvas.create_line(x1, y1, x2, y2, dash=(8, 5), width=4,
                                    fill=MOVE_LINE, capstyle='round')
        # 棋子
        for pos in range(25):
            d = self.dpos(pos)
            if (self.wolves >> pos) & 1:
                self._draw_piece(d, 'wolf', self.selected == pos)
            elif (self.sheep >> pos) & 1:
                self._draw_piece(d, 'sheep', self.selected == pos)
        # 选中:合法落点提示(空位=圆点,可吃=圆环)+ 高亮框
        if self.selected is not None and not self.game_over:
            turn = self.cur_turn()
            if turn == WOLF:
                moves = wolf_moves(self.wolves, self.sheep)
                for frm, to, cap in moves:
                    if frm != self.selected:
                        continue
                    d = self.dpos(to)
                    x = BO + (d % 5) * 100
                    y = BO + (d // 5) * 100
                    if cap:
                        self.canvas.create_oval(x - 34, y - 34, x + 34, y + 34,
                                                outline=SEL_EDGE, width=3)
                    else:
                        self.canvas.create_oval(x - 9, y - 9, x + 9, y + 9,
                                                fill='#000000', stipple='gray50',
                                                outline='')
            else:
                for frm, to in sheep_moves(self.wolves, self.sheep):
                    if frm != self.selected:
                        continue
                    d = self.dpos(to)
                    x = BO + (d % 5) * 100
                    y = BO + (d // 5) * 100
                    self.canvas.create_oval(x - 9, y - 9, x + 9, y + 9,
                                            fill='#000000', stipple='gray50',
                                            outline='')
            d = self.dpos(self.selected)
            r, c = divmod(d, 5)
            x = BO + c * 100
            y = BO + r * 100
            self.canvas.create_rectangle(x - 40, y - 40, x + 40, y + 40,
                                         outline=SEL_EDGE, width=2)
        # 分析箭头(画在棋子上层,终点=棋子中心):绿=当前方最佳, 红=对方应对
        # 悬停候选时临时隐藏第一支(最佳)箭头,用黄色预览箭头替代,避免三箭拥挤
        if self.analysis_on() and not self.game_over and self.pv_moves:
            colors = ['#1FA23C', '#E4572E']
            idxs = list(range(min(2, len(self.pv_moves))))
            if self.hover_mv is not None and 0 in idxs:
                idxs.remove(0)
            # 第一支箭头必须与候选面板第一手一致(面板=当前局面的同步
            # 最优);分析数据若过期(异步竞态/浏览)自动纠正。变招模式下
            # 才允许显示第N档变招箭头。
            use_panel = ((self.variant_override or 0) == 0
                         and bool(self._cand_cache))
            for i in idxs:
                if i == 0 and use_panel:
                    mv = self._cand_cache[0]
                else:
                    mv = self.pv_moves[i]
                if mv is None:
                    continue
                self._draw_arrow(mv[0], mv[1], colors[i],
                                 width=6 if i == 0 else 5)
        # 悬停预览箭头(金黄色)
        if self.hover_mv is not None and not self.game_over:
            self._draw_arrow(self.hover_mv[0], self.hover_mv[1], '#F5C518',
                             width=6)
        # 状态:局面判定
        if self.editing:
            first = "狼" if self.turn_bias == 0 else "羊"
            self.status_label.config(
                text=f"编辑模式:点击格子循环 空→狼→羊→空 | 先手:{first} | "
                     f"狼3只、羊3~15只 | 完成后点'完成'")
        elif not self.game_over:
            turn = self.cur_turn()
            v = endgame.lookup(self.wolves, self.sheep, turn)
            k = popcount(self.sheep)
            if v == ONGOING:
                tag = f"未破解层(羊{k}只,AI用搜索)"
            else:
                tag = f"{WIN_NAMES[v]}(羊{k}只)"
                if v == DRAW:
                    tag += "(限步判狼胜)"
                d = endgame.lookup_dist(self.wolves, self.sheep, turn)
                if d > 0 and v != DRAW:
                    tag += f" · 距终局{d}步"
            who = "狼" if turn == WOLF else "羊"
            step = f" · 第{self.move_count + 1}/{self.move_limit}步"
            if self.ai_thinking:
                self.status_label.config(text=f"AI思考中…({tag}){step}")
            else:
                self.status_label.config(text=f"轮到{who} · {tag}{step}")


if __name__ == "__main__":
    import sys

    import multiprocessing
    multiprocessing.freeze_support()
    try:
        import parallel_score
        parallel_score.enable()
    except Exception:
        pass

    ttdir0 = endgame.default_outdir()

    if "--unpack-only" in sys.argv:
        # 仅解压 .zst 数据表(打包自检用,不开游戏)
        tabpack.ensure_tables(ttdir0, progress=print)
        print("unpack done")
        sys.exit(0)

    if "--selftest" in sys.argv:
        # 无界面自检(软件包构建后的端到端验证):先解压(如有),再验证引擎
        tabpack.ensure_tables(ttdir0, progress=print)
        eng = Engine()
        v0 = endgame.lookup(INIT_WOLVES, INIT_SHEEP, WOLF)
        mv, info = eng.best_move(INIT_WOLVES, INIT_SHEEP, WOLF, ply_budget=150)
        # 初始局面旧规则=和棋(首着必为中心吃 C5→C3);新规则重算后可能=狼胜
        if v0 == DRAW:
            ok = (mv == (2, 12, True))
        else:
            ok = (v0 == WOLF_WIN and mv is not None and mv[0] is not None
                  and info["value"] == WOLF_WIN)
        print("selftest:", "OK" if ok else f"FAIL v0={v0} mv={mv}")
        # 多核并行评分自检:走3手到多候选局面,触发批量并行
        try:
            import parallel_score
            parallel_score.enable()
            w2, s2 = apply_wolf_move(INIT_WOLVES, INIT_SHEEP, 2, 12)
            w3, s3 = apply_sheep_move(w2, s2, 11, 6)
            w4, s4 = apply_wolf_move(w3, s3, 3, 13)
            mv2, info2 = eng.best_move(w4, s4, SHEEP, history=(),
                                       score_depth=5)
            par = parallel_score.is_parallel_active()
            print("parallel selftest:", "OK" if mv2 else "FAIL",
                  "| 多核池:", "已启用" if par else "未启用(串行回退)")
        except Exception as e:
            print("parallel selftest: FAIL", e)
        sys.exit(0 if ok else 1)

    # 首次运行:自动解压 .zst 数据表(仅打包版分发用)
    ttdir = ttdir0
    pending = []
    if os.path.isdir(ttdir):
        pending = [n for n in os.listdir(ttdir)
                   if n.endswith(".zst")
                   and not os.path.exists(os.path.join(ttdir, n[:-4]))]
    if pending:
        root = tk.Tk()
        root.title("首次安装")
        root.geometry("620x140")
        lbl = tk.Label(root, text="正在解压数据表(仅首次,约2~5分钟,请勿关闭)…",
                       font=('Arial', 12))
        lbl.pack(padx=30, pady=20, fill=tk.BOTH, expand=True)
        root.update()

        def prog(t):
            lbl.config(text=t)
            root.update()

        try:
            tabpack.ensure_tables(ttdir, progress=prog)
        except PermissionError:
            root.destroy()
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "首次安装失败",
                "无法写入游戏目录(权限不足)。\n\n"
                "请把整个游戏文件夹移到可写的位置(如 D 盘根目录、桌面、"
                "文档目录),不要在 C:\\Program Files 等受保护目录里运行。")
            root.destroy()
            sys.exit(1)
        except Exception as e:
            root.destroy()
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "首次安装失败",
                f"数据表解压失败:{e}\n\n"
                "可能原因:磁盘空间不足 / 压缩包损坏(传输不完整,请重新拷贝) / "
                "目录只读。\n修复后可重新双击启动,程序会自动续装。")
            root.destroy()
            sys.exit(1)
        root.destroy()

    root = tk.Tk()
    game = Game(root)
    root.mainloop()

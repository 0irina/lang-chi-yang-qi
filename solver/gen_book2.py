# -*- coding: utf-8 -*-
"""由 dfs_probe_report.txt 的 120 手线生成"次选高压"开局书 opening_book2.py。
- 校验:逐手回放,羊招合法且走后和棋,狼招为真实正招(该点狼正招数<=2);
- 只收录"主选书(opening_book.BOOK)中不存在"的局面;
- 收录走法走后狼正招数<=2(整体持续高压,偶尔有2条可选)。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import endgame
from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW,
                   pos_name, wolf_moves, sheep_moves,
                   apply_wolf_move, apply_sheep_move, popcount,
                   INIT_WOLVES, INIT_SHEEP)
import opening_book

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "dfs_probe_report.txt")


def cell(s):
    col = ord(s[0]) - 65
    r0 = 5 - int(s[1])
    return r0 * 5 + col


def parse_line(path):
    text = open(path, encoding="utf-8").read().strip().splitlines()
    line = text[-1] if text else ""
    toks = []
    for t in line.split():
        if t.startswith("狼") or t.startswith("羊"):
            who = t[0]
            mv = re.sub(r"\(正招\d\)", "", t[1:])
            a, b = mv.replace("吃", "").split("→")
            cap = "吃" in mv
            toks.append((who, cell(a), cell(b), cap))
    return toks


def wolf_draw_list(w, s):
    out = []
    for a, b, cap in wolf_moves(w, s):
        w2, s2 = apply_wolf_move(w, s, a, b)
        if popcount(s2) <= 3:
            out.append((a, b, cap))
            continue
        if endgame.lookup(w2, s2, SHEEP) == DRAW:
            out.append((a, b, cap))
    return out


def main():
    endgame.load_tables()
    toks = parse_line(SRC)
    if toks and toks[0][0] == "狼" and toks[0][1:3] == (2, 12):
        toks = toks[1:]   # 首着 C5→C3 已在下面预走
    print(f"解析 {len(toks)} 个走法 token")
    w, s = apply_wolf_move(INIT_WOLVES, INIT_SHEEP, 2, 12)
    book2 = {}
    n_skip = 0
    wc_max = 0
    for who, a, b, cap in toks:
        if who == "羊":
            assert any((x, y) == (a, b) for x, y in sheep_moves(w, s)), \
                f"羊非法 {pos_name(a)}→{pos_name(b)}"
            w2, s2 = apply_sheep_move(w, s, a, b)
            assert endgame.lookup(w2, s2, WOLF) == DRAW
            bm = opening_book.BOOK.get((w, s))
            if bm and (a, b) in bm:
                n_skip += 1   # 该走法已是主选走法,不重复收录
            else:
                book2.setdefault((w, s), []).append((a, b))
            w, s = w2, s2
        else:
            assert any((x, y) == (a, b) for x, y, c2 in wolf_moves(w, s)), \
                f"狼非法 {pos_name(a)}→{pos_name(b)}"
            dm = wolf_draw_list(w, s)
            wc_max = max(wc_max, len(dm))
            assert len(dm) <= 2, f"狼正招数 {len(dm)} > 2"
            assert (a, b) in [(x, y) for x, y, c2 in dm], \
                f"狼走法 {pos_name(a)}→{pos_name(b)} 非正招"
            w, s = apply_wolf_move(w, s, a, b)
            assert endgame.lookup(w, s, SHEEP) == DRAW
    print(f"线长校验 OK;沿线狼正招数最大 {wc_max};"
          f"主选书重叠跳过 {n_skip};次选条目 {len(book2)}")

    # 镜像补全:5x5 棋盘左右对称,次选书两侧都要有
    def _mpos(p):
        return (p // 5) * 5 + (4 - p % 5)

    def _mstate(w, s):
        mw = ms = 0
        x = w
        while x:
            lsb = x & -x
            mw |= 1 << _mpos(lsb.bit_length() - 1)
            x ^= lsb
        x = s
        while x:
            lsb = x & -x
            ms |= 1 << _mpos(lsb.bit_length() - 1)
            x ^= lsb
        return mw, ms

    added = 0
    for (w2, s2), ms in list(book2.items()):
        mw, mss = _mstate(w2, s2)
        tgt = book2.setdefault((mw, mss), [])
        for a, b in ms:
            mmv = (_mpos(a), _mpos(b))
            if mmv not in tgt:
                tgt.append(mmv)
                added += 1
    print(f"次选书镜像补全: 新增 {added} 个走法,共 {len(book2)} 个局面")

    lines = [
        "# -*- coding: utf-8 -*-",
        '"""次选高压开局书(由 dfs_probe_report.txt / gen_book2.py 生成)。',
        "羊走局面 (w, s) -> 走法列表:走后仍和棋,狼正招数<=2(压力略小于",
        "主选书的'唯一正招'),整体仍持续高压。主选书(opening_book.BOOK)",
        "优先;本表只收录主选书没有的局面。全部走法经全破解表校验。",
        '"""',
        "BOOK2 = {",
    ]
    for (w2, s2), ms in sorted(book2.items()):
        lines.append(f"    ({w2}, {s2}): {ms!r},")
    lines.append("}")
    with open(os.path.join(HERE, "opening_book2.py"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("opening_book2.py 生成完毕")


if __name__ == "__main__":
    main()

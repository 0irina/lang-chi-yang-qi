# -*- coding: utf-8 -*-
"""由 corridor_book.json 生成 opening_book.py(引擎导入的纯数据模块)。
每局面只保留"线路走廊长度最大"的走法档,供引擎在这些走法间轮换。"""
import json
import os

here = os.path.dirname(os.path.abspath(__file__))
book = json.load(open(os.path.join(here, "corridor_book.json"),
                      encoding="utf-8"))
out = {}
for k, moves in book.items():
    w, s = map(int, k.split(":"))
    best = max(m[2] for m in moves)
    out[(w, s)] = [(m[0], m[1]) for m in moves if m[2] == best]

lines = [
    "# -*- coding: utf-8 -*-",
    '"""高压走廊开局书(由 corridor_search.py / gen_book.py 生成)。',
    "羊走局面 (w, s) -> 该局面下保持\"狼唯一正招\"的最长走廊走法列表;",
    "引擎在书内轮换走法(防背谱),书外回到常规和棋策略。",
    "全部走法经全破解表校验:走后仍和棋,且狼若走唯一正招以外的",
    "任何着法即羊胜。切勿手工编辑。",
    '"""',
    "BOOK = {",
]
for (w, s), ms in sorted(out.items()):
    lines.append(f"    ({w}, {s}): {ms!r},")
lines.append("}")
path = os.path.join(here, "opening_book.py")
with open(path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print(f"opening_book.py 生成完毕: {len(out)} 个局面条目")
